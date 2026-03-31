from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.gesture_remap.pose_templates import FINGER_CHAINS, HAND_LANDMARK_COUNT, build_preview_templates
from paths import resource


def _safe_unit(vector: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        if fallback is None:
            return np.zeros(3, dtype=np.float32)
        return np.asarray(fallback, dtype=np.float32)
    return (vector / norm).astype(np.float32)


def _clamp_direction(previous: np.ndarray, candidate: np.ndarray, max_angle_deg: float) -> np.ndarray:
    prev = _safe_unit(previous)
    curr = _safe_unit(candidate, fallback=prev)
    dot = float(np.clip(np.dot(prev, curr), -1.0, 1.0))
    angle = math.degrees(math.acos(dot))
    if angle <= max_angle_deg or angle < 1e-6:
        return curr

    axis = np.cross(prev, curr)
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm < 1e-6:
        return prev
    axis = axis / axis_norm
    radians = math.radians(max_angle_deg)
    cos_theta = math.cos(radians)
    sin_theta = math.sin(radians)
    rotated = (
        (prev * cos_theta)
        + (np.cross(axis, prev) * sin_theta)
        + (axis * np.dot(axis, prev) * (1.0 - cos_theta))
    )
    return _safe_unit(rotated, fallback=prev)


def _rotation_matrix_from_vectors(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source_unit = _safe_unit(source, fallback=np.asarray((0.0, 1.0, 0.0), dtype=np.float32))
    target_unit = _safe_unit(target, fallback=source_unit)
    dot = float(np.clip(np.dot(source_unit, target_unit), -1.0, 1.0))
    if dot > 0.9999:
        return np.eye(3, dtype=np.float32)
    if dot < -0.9999:
        arbitrary = np.asarray((1.0, 0.0, 0.0), dtype=np.float32)
        if abs(float(np.dot(source_unit, arbitrary))) > 0.95:
            arbitrary = np.asarray((0.0, 1.0, 0.0), dtype=np.float32)
        axis = _safe_unit(np.cross(source_unit, arbitrary), fallback=np.asarray((0.0, 0.0, 1.0), dtype=np.float32))
        return _rotation_matrix_from_axis_angle(axis, math.pi)

    axis = _safe_unit(np.cross(source_unit, target_unit), fallback=np.asarray((0.0, 0.0, 1.0), dtype=np.float32))
    angle = math.acos(dot)
    return _rotation_matrix_from_axis_angle(axis, angle)


def _rotation_matrix_from_axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = _safe_unit(axis, fallback=np.asarray((0.0, 0.0, 1.0), dtype=np.float32))
    x, y, z = axis
    cos_theta = math.cos(angle)
    sin_theta = math.sin(angle)
    one_minus_cos = 1.0 - cos_theta
    return np.asarray(
        [
            [
                cos_theta + (x * x * one_minus_cos),
                (x * y * one_minus_cos) - (z * sin_theta),
                (x * z * one_minus_cos) + (y * sin_theta),
            ],
            [
                (y * x * one_minus_cos) + (z * sin_theta),
                cos_theta + (y * y * one_minus_cos),
                (y * z * one_minus_cos) - (x * sin_theta),
            ],
            [
                (z * x * one_minus_cos) - (y * sin_theta),
                (z * y * one_minus_cos) + (x * sin_theta),
                cos_theta + (z * z * one_minus_cos),
            ],
        ],
        dtype=np.float32,
    )


def _point_to_segment_distance(points: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    segment = end - start
    denominator = float(np.dot(segment, segment))
    if denominator < 1e-8:
        return np.linalg.norm(points - start[None, :], axis=1)
    t = np.clip(np.sum((points - start[None, :]) * segment[None, :], axis=1) / denominator, 0.0, 1.0)
    closest = start[None, :] + (segment[None, :] * t[:, None])
    return np.linalg.norm(points - closest, axis=1)


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    magnitudes = np.linalg.norm(vectors, axis=1, keepdims=True)
    magnitudes[magnitudes < 1e-6] = 1.0
    return (vectors / magnitudes).astype(np.float32)


def _recompute_vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    triangles = vertices[faces]
    face_normals = np.cross(
        triangles[:, 1] - triangles[:, 0],
        triangles[:, 2] - triangles[:, 0],
    )
    face_lengths = np.linalg.norm(face_normals, axis=1, keepdims=True)
    face_lengths[face_lengths < 1e-6] = 1.0
    face_normals = face_normals / face_lengths

    vertex_normals = np.zeros_like(vertices, dtype=np.float32)
    np.add.at(vertex_normals, faces[:, 0], face_normals)
    np.add.at(vertex_normals, faces[:, 1], face_normals)
    np.add.at(vertex_normals, faces[:, 2], face_normals)
    return _normalize_rows(vertex_normals)


def _pairwise_distances(points_a: np.ndarray, points_b: np.ndarray) -> np.ndarray:
    deltas = points_a[:, None, :] - points_b[None, :, :]
    return np.linalg.norm(deltas, axis=2).astype(np.float32)


def _project_point_to_plane(point: np.ndarray, plane_point: np.ndarray, plane_normal: np.ndarray) -> np.ndarray:
    normal = _safe_unit(plane_normal, fallback=np.asarray((1.0, 0.0, 0.0), dtype=np.float32))
    offset = point - plane_point
    distance = float(np.dot(offset, normal))
    return (point - (normal * distance)).astype(np.float32)


def _project_points_to_plane(points: np.ndarray, plane_point: np.ndarray, plane_normal: np.ndarray) -> np.ndarray:
    return np.asarray([_project_point_to_plane(point, plane_point, plane_normal) for point in points], dtype=np.float32)


def _smoothstep(edge0: float, edge1: float, values: np.ndarray) -> np.ndarray:
    if abs(edge1 - edge0) < 1e-6:
        return np.ones_like(values, dtype=np.float32)
    normalized = np.clip((values - edge0) / (edge1 - edge0), 0.0, 1.0).astype(np.float32)
    return (normalized * normalized * (3.0 - (2.0 * normalized))).astype(np.float32)


def _rbf_kernel(distances: np.ndarray) -> np.ndarray:
    # Polyharmonic radial basis in 3D. This is smooth, stable for small anchor
    # counts, and works well for editor-driven landmark repositioning.
    return distances.astype(np.float32)


@dataclass(frozen=True)
class HandRigBoneNode:
    name: str
    start: int
    end: int
    radius: float


@dataclass(frozen=True)
class HandEditorAssetManifest:
    asset_path: Path
    asset_version: str
    mesh_asset_keys: dict[str, str]
    mesh_nodes: dict[str, str]
    bone_nodes: tuple[HandRigBoneNode, ...]
    anchor_nodes: dict[int, str]
    neutral_landmarks: np.ndarray
    neutral_anchor_positions: np.ndarray

    @property
    def display_mesh_key(self) -> str:
        return self.mesh_asset_keys["display_hand"]

    @property
    def interaction_mesh_key(self) -> str:
        return self.mesh_asset_keys["interaction_hand"]

    @classmethod
    def load(cls, manifest_path: Path | None = None) -> "HandEditorAssetManifest":
        path = manifest_path or resource("frontend/assets/gesture_editor/hand_manifest.json")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        anchor_nodes = {int(index): str(name) for index, name in data["anchor_nodes"].items()}
        neutral = np.asarray(data["neutral_landmarks"], dtype=np.float32)
        neutral_anchors = np.asarray(data["neutral_anchor_positions"], dtype=np.float32)
        if neutral.shape != (HAND_LANDMARK_COUNT, 3):
            raise ValueError(f"Expected neutral landmarks shape {(HAND_LANDMARK_COUNT, 3)}, got {neutral.shape}")
        if neutral_anchors.shape != (HAND_LANDMARK_COUNT, 3):
            raise ValueError(
                f"Expected neutral anchor positions shape {(HAND_LANDMARK_COUNT, 3)}, got {neutral_anchors.shape}"
            )
        return cls(
            asset_path=Path(path).with_name(str(data["asset_file"])).resolve(),
            asset_version=str(data.get("editor_asset_version", "unknown")),
            mesh_asset_keys={str(key): str(value) for key, value in data.get("mesh_asset_keys", {}).items()},
            mesh_nodes={str(key): str(value) for key, value in data["mesh_nodes"].items()},
            bone_nodes=tuple(
                HandRigBoneNode(
                    name=str(entry["name"]),
                    start=int(entry["start"]),
                    end=int(entry["end"]),
                    radius=float(entry["radius"]),
                )
                for entry in data["bone_nodes"]
            ),
            anchor_nodes=anchor_nodes,
            neutral_landmarks=neutral,
            neutral_anchor_positions=neutral_anchors,
        )


class HandRigSolver:
    FINGER_CHAINS = (
        (1, 2, 3, 4),
        (5, 6, 7, 8),
        (9, 10, 11, 12),
        (13, 14, 15, 16),
        (17, 18, 19, 20),
    )

    JOINT_LIMITS = {
        (1, 2, 3, 4): (84.0, 96.0, 102.0),
        (5, 6, 7, 8): (84.0, 124.0, 112.0),
        (9, 10, 11, 12): (82.0, 122.0, 112.0),
        (13, 14, 15, 16): (86.0, 126.0, 114.0),
        (17, 18, 19, 20): (90.0, 130.0, 118.0),
    }

    def __init__(self, manifest: HandEditorAssetManifest):
        self.manifest = manifest
        self.full_chains = tuple((0,) + chain for chain in self.FINGER_CHAINS)
        self.segment_lengths = {
            (bone.start, bone.end): float(
                np.linalg.norm(manifest.neutral_landmarks[bone.end] - manifest.neutral_landmarks[bone.start])
            )
            for bone in manifest.bone_nodes
        }
        self._neutral_landmarks = manifest.neutral_landmarks.astype(np.float32)
        _neutral_x, neutral_y, self._neutral_palm_normal = self.palm_basis(self._neutral_landmarks)
        self._neutral_directions = {
            (start, end): _safe_unit(
                self._neutral_landmarks[end] - self._neutral_landmarks[start],
                fallback=np.asarray((0.0, 1.0, 0.0), dtype=np.float32),
            )
            for start, end in self.segment_lengths
        }
        self._neutral_forearm_axis = _safe_unit(-neutral_y, fallback=np.asarray((0.0, -1.0, 0.0), dtype=np.float32))
        self._forearm_length = max(
            0.55,
            float(
                np.mean(
                    [
                        self.segment_lengths[(0, 1)],
                        self.segment_lengths[(0, 5)],
                        self.segment_lengths[(0, 9)],
                        self.segment_lengths[(0, 13)],
                        self.segment_lengths[(0, 17)],
                    ]
                )
            ),
        )
        self._forearm_base = (
            self._neutral_landmarks[0] + (self._neutral_forearm_axis * self._forearm_length)
        ).astype(np.float32)

    def _joint_limits_for_chain(self, chain: tuple[int, ...]) -> tuple[float, ...]:
        target = chain[1:] if chain and chain[0] == 0 else chain
        if target in self.JOINT_LIMITS:
            return self.JOINT_LIMITS[target]

        for reference_chain, limits in self.JOINT_LIMITS.items():
            if tuple(reference_chain[: len(target)]) == tuple(target):
                required = max(len(chain) - 2, 0)
                return limits[:required]
        raise KeyError(f"No joint limits available for chain {chain}")

    def _solve_full_chain_to_tip(self, chain: tuple[int, ...], points: np.ndarray) -> np.ndarray:
        lengths = np.asarray(
            [self.segment_lengths[(start, end)] for start, end in zip(chain[:-1], chain[1:])],
            dtype=np.float32,
        )
        total_length = float(np.sum(lengths))
        root = points[chain[0]].astype(np.float32)
        target = points[chain[-1]].astype(np.float32)

        neutral_tip_direction = self._neutral_landmarks[chain[-1]] - self._neutral_landmarks[chain[0]]
        plane_normal = np.cross(neutral_tip_direction, self._neutral_palm_normal)
        plane_normal = _safe_unit(plane_normal, fallback=np.asarray((1.0, 0.0, 0.0), dtype=np.float32))
        target = _project_point_to_plane(target, root, plane_normal)
        solved = _project_points_to_plane(points[list(chain)].astype(np.float32).copy(), root, plane_normal)

        if float(np.linalg.norm(target - root)) >= total_length - 1e-6:
            direction = _safe_unit(target - root, fallback=self._neutral_directions[(chain[0], chain[1])])
            solved[0] = root
            for offset, length in enumerate(lengths, start=1):
                solved[offset] = solved[offset - 1] + (direction * length)
            return solved

        solved[0] = root
        solved[-1] = target
        for _ in range(14):
            solved[-1] = target
            for segment_index in range(len(lengths) - 1, -1, -1):
                end = solved[segment_index + 1]
                start = solved[segment_index]
                direction = _safe_unit(start - end, fallback=self._neutral_directions[(chain[segment_index], chain[segment_index + 1])])
                solved[segment_index] = _project_point_to_plane(end + (direction * lengths[segment_index]), root, plane_normal)

            solved[0] = root
            previous_direction = None
            limits = self._joint_limits_for_chain(chain)
            for segment_index, length in enumerate(lengths):
                desired_direction = solved[segment_index + 1] - solved[segment_index]
                if segment_index == 0:
                    fallback = self._neutral_directions[(chain[segment_index], chain[segment_index + 1])]
                    direction = _safe_unit(desired_direction, fallback=fallback)
                else:
                    direction = _clamp_direction(previous_direction, desired_direction, limits[segment_index - 1])
                solved[segment_index + 1] = _project_point_to_plane(
                    solved[segment_index] + (direction * length),
                    root,
                    plane_normal,
                )
                previous_direction = direction

            if float(np.linalg.norm(solved[-1] - target)) <= 1e-4:
                break

        return solved

    def _solve_prefix_chain(self, chain: tuple[int, ...], points: np.ndarray, edited_index: int) -> np.ndarray:
        edited_offset = chain.index(edited_index)
        working_points = points.astype(np.float32).copy()
        if edited_offset == len(chain) - 1:
            root = working_points[chain[0]].copy()
            target = working_points[chain[-1]].copy()
            for local_index in range(1, len(chain) - 1):
                ratio = float(local_index) / float(len(chain) - 1)
                target_hint = root + ((target - root) * ratio)
                neutral_hint = self._neutral_landmarks[chain[local_index]]
                bias_strength = 0.18 + (0.28 * ratio)
                working_points[chain[local_index]] = (
                    (target_hint * bias_strength) + (neutral_hint * (1.0 - bias_strength))
                ).astype(np.float32)

        prefix = chain[: edited_offset + 1]
        solved_prefix = self._solve_full_chain_to_tip(prefix, working_points)
        solved_chain = working_points[list(chain)].astype(np.float32).copy()
        solved_chain[: edited_offset + 1] = solved_prefix

        if edited_offset == len(chain) - 1:
            return solved_chain

        limits = self._joint_limits_for_chain(chain)
        if edited_offset == 0:
            previous_direction = self._neutral_directions[(chain[0], chain[1])]
        else:
            previous_direction = _safe_unit(
                solved_chain[edited_offset] - solved_chain[edited_offset - 1],
                fallback=self._neutral_directions[(chain[edited_offset - 1], chain[edited_offset])],
            )
        for local_index in range(edited_offset, len(chain) - 1):
            start = chain[local_index]
            end = chain[local_index + 1]
            length = self.segment_lengths[(start, end)]
            desired_direction = points[end] - points[start]
            if local_index == 0:
                direction = _safe_unit(desired_direction, fallback=self._neutral_directions[(start, end)])
            else:
                limit_index = min(local_index - 1, len(limits) - 1)
                direction = _clamp_direction(previous_direction, desired_direction, limits[limit_index])
            solved_chain[local_index + 1] = solved_chain[local_index] + (direction * length)
            previous_direction = direction
        return solved_chain

    def _solve_wrist_pose(self, target_landmarks: np.ndarray, previous_landmarks: np.ndarray | None) -> np.ndarray:
        if previous_landmarks is None:
            return np.asarray(target_landmarks, dtype=np.float32).copy()

        previous = np.asarray(previous_landmarks, dtype=np.float32).copy()
        target = np.asarray(target_landmarks, dtype=np.float32).copy()
        current_wrist = previous[0]
        desired_wrist = target[0]
        current_vector = current_wrist - self._forearm_base
        current_radius = max(float(np.linalg.norm(current_vector)), self._forearm_length)
        desired_direction = _safe_unit(
            desired_wrist - self._forearm_base,
            fallback=_safe_unit(current_vector, fallback=-self._neutral_forearm_axis),
        )
        solved_wrist = (self._forearm_base + (desired_direction * current_radius)).astype(np.float32)
        rotation = _rotation_matrix_from_vectors(current_vector, solved_wrist - self._forearm_base)

        solved = previous.copy()
        relative = previous - current_wrist[None, :]
        solved[0] = solved_wrist
        solved[1:] = solved_wrist[None, :] + (relative[1:] @ rotation.T)
        return solved.astype(np.float32)

    def solve_landmarks(
        self,
        landmarks: np.ndarray,
        edited_index: int | None = None,
        previous_landmarks: np.ndarray | None = None,
    ) -> np.ndarray:
        points = np.asarray(landmarks, dtype=np.float32).copy()
        if points.shape != (HAND_LANDMARK_COUNT, 3):
            raise ValueError(f"Expected hand landmarks shape {(HAND_LANDMARK_COUNT, 3)}, got {points.shape}")

        if edited_index == 0:
            return self._solve_wrist_pose(points, previous_landmarks)

        solved = points.copy()
        solved[0] = points[0]

        for chain in self.full_chains:
            if edited_index in chain[1:]:
                solved_chain = self._solve_prefix_chain(chain, points, int(edited_index))
            else:
                solved_chain = self._solve_full_chain_to_tip(chain, points)
            for local_index, landmark_index in enumerate(chain):
                solved[landmark_index] = solved_chain[local_index]

        return solved

    def palm_basis(self, landmarks: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        wrist = landmarks[0]
        index_mcp = landmarks[5]
        middle_mcp = landmarks[9]
        pinky_mcp = landmarks[17]

        x_axis = _safe_unit(pinky_mcp - index_mcp, fallback=np.asarray((1.0, 0.0, 0.0), dtype=np.float32))
        y_axis = _safe_unit(middle_mcp - wrist, fallback=np.asarray((0.0, 1.0, 0.0), dtype=np.float32))
        z_axis = _safe_unit(np.cross(x_axis, y_axis), fallback=np.asarray((0.0, 0.0, 1.0), dtype=np.float32))
        y_axis = _safe_unit(np.cross(z_axis, x_axis), fallback=y_axis)
        return x_axis, y_axis, z_axis


@dataclass(frozen=True)
class HandMeshAsset:
    vertices: np.ndarray
    normals: np.ndarray
    indices: np.ndarray


@dataclass(frozen=True)
class HandDisplayAsset:
    mesh: HandMeshAsset
    anchor_positions: np.ndarray


@dataclass(frozen=True)
class HandInteractionMesh:
    mesh: HandMeshAsset


def load_hand_mesh_assets(manifest: HandEditorAssetManifest) -> dict[str, HandMeshAsset]:
    payload = np.load(manifest.asset_path)
    meshes: dict[str, HandMeshAsset] = {}
    for key in manifest.mesh_asset_keys.values():
        vertices = np.asarray(payload[f"{key}_vertices"], dtype=np.float32)
        normals = np.asarray(payload[f"{key}_normals"], dtype=np.float32)
        indices = np.asarray(payload[f"{key}_indices"], dtype=np.uint32)
        if vertices.size == 0 or indices.size == 0:
            raise ValueError(f"Mesh asset '{key}' is empty")
        meshes[key] = HandMeshAsset(vertices=vertices, normals=normals, indices=indices)
    return meshes


def build_hand_assets(
    manifest: HandEditorAssetManifest,
    mesh_assets: dict[str, HandMeshAsset],
) -> tuple[HandDisplayAsset, HandInteractionMesh]:
    display_key = manifest.display_mesh_key
    interaction_key = manifest.interaction_mesh_key
    if display_key not in mesh_assets:
        raise ValueError(f"Display hand mesh '{display_key}' not found in packed assets")
    if interaction_key not in mesh_assets:
        raise ValueError(f"Interaction hand mesh '{interaction_key}' not found in packed assets")

    display_mesh = mesh_assets[display_key]
    interaction_mesh = mesh_assets[interaction_key]
    display_extents = np.max(display_mesh.vertices, axis=0) - np.min(display_mesh.vertices, axis=0)
    if len(display_mesh.vertices) < 1000 or len(display_mesh.indices) < 3000:
        raise ValueError("Display hand mesh is unexpectedly small")
    if float(np.max(display_extents)) < 1.0:
        raise ValueError("Display hand mesh bounds are unexpectedly tiny")
    if len(interaction_mesh.vertices) < 50 or len(interaction_mesh.indices) < 150:
        raise ValueError("Interaction hand mesh is unexpectedly small")
    return (
        HandDisplayAsset(mesh=display_mesh, anchor_positions=manifest.neutral_anchor_positions.copy()),
        HandInteractionMesh(mesh=interaction_mesh),
    )


class HandMeshDeformer:
    """Bone-weighted surface deformation for the imported hand mesh."""

    MAX_INFLUENCES = 4
    THUMB_CHAIN_ID = 0

    def __init__(
        self,
        manifest: HandEditorAssetManifest,
        display_asset: HandDisplayAsset,
        interaction_asset: HandInteractionMesh,
    ):
        self.manifest = manifest
        self._solver = HandRigSolver(manifest)
        self.display_asset = display_asset
        self.interaction_asset = interaction_asset
        self.indices = np.asarray(display_asset.mesh.indices, dtype=np.uint32)
        self.faces = self.indices.reshape(-1, 3)
        self.neutral_vertices = np.asarray(display_asset.mesh.vertices, dtype=np.float32)
        self.neutral_anchor_positions = np.asarray(display_asset.anchor_positions, dtype=np.float32)
        self._neutral_landmarks = self.manifest.neutral_landmarks.astype(np.float32)
        self._neutral_x, self._neutral_y, self._neutral_z = self._solver.palm_basis(self._neutral_landmarks)
        self._forearm_blend = self._build_forearm_blend()
        self._bone_indices = np.asarray(
            [(bone.start, bone.end) for bone in self.manifest.bone_nodes],
            dtype=np.int32,
        )
        self._neutral_starts = self._neutral_landmarks[self._bone_indices[:, 0]]
        self._neutral_ends = self._neutral_landmarks[self._bone_indices[:, 1]]
        self._neutral_segments = self._neutral_ends - self._neutral_starts
        self._neutral_lengths = np.linalg.norm(self._neutral_segments, axis=1).astype(np.float32)
        self._neutral_lengths[self._neutral_lengths < 1e-6] = 1e-6
        self._neutral_directions = (self._neutral_segments / self._neutral_lengths[:, None]).astype(np.float32)
        self._bone_chain_ids = np.asarray(
            [self._chain_id_for_landmark(int(bone.end)) for bone in self.manifest.bone_nodes],
            dtype=np.int32,
        )
        self._chain_bone_indices = [
            np.where(
                (self._bone_chain_ids == chain_id)
                & (self._bone_indices[:, 0] != 0)
            )[0].astype(np.int32)
            for chain_id in range(len(FINGER_CHAINS))
        ]
        (
            self._vertex_weights,
            self._vertex_segment_params,
            self._vertex_segment_offsets,
            self._vertex_chain_assignments,
            self._vertex_chain_blends,
        ) = self._build_vertex_attachment_data()

    def _build_forearm_blend(self) -> np.ndarray:
        along_hand = np.dot(self.neutral_vertices - self._neutral_landmarks[0][None, :], self._neutral_y)
        low = -self._solver._forearm_length * 0.32
        high = self._solver._forearm_length * 0.10
        return _smoothstep(low, high, along_hand).astype(np.float32)

    @staticmethod
    def _chain_id_for_landmark(landmark_index: int) -> int:
        for chain_id, chain in enumerate(FINGER_CHAINS):
            if landmark_index in chain:
                return chain_id
        raise ValueError(f"Landmark {landmark_index} does not map to a finger chain")

    def _build_vertex_attachment_data(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        vertex_count = len(self.neutral_vertices)
        bone_count = len(self._bone_indices)
        distances = np.zeros((vertex_count, bone_count), dtype=np.float32)
        segment_params = np.zeros((vertex_count, bone_count), dtype=np.float32)
        segment_offsets = np.zeros((vertex_count, bone_count, 3), dtype=np.float32)
        influence_radii = np.asarray(
            [max(bone.radius * 2.4, 0.12) for bone in self.manifest.bone_nodes],
            dtype=np.float32,
        )

        for bone_index, (start, end) in enumerate(self._bone_indices):
            start_point = self._neutral_landmarks[start]
            end_point = self._neutral_landmarks[end]
            segment = end_point - start_point
            length_sq = float(np.dot(segment, segment))
            if length_sq < 1e-8:
                segment = np.asarray((0.0, 1.0, 0.0), dtype=np.float32)
                length_sq = 1.0

            deltas = self.neutral_vertices - start_point[None, :]
            t = np.clip(np.sum(deltas * segment[None, :], axis=1) / length_sq, 0.0, 1.0)
            closest = start_point[None, :] + (t[:, None] * segment[None, :])
            segment_params[:, bone_index] = t.astype(np.float32)
            segment_offsets[:, bone_index, :] = (self.neutral_vertices - closest).astype(np.float32)
            distances[:, bone_index] = _point_to_segment_distance(self.neutral_vertices, start_point, end_point)

        weights = np.exp(-np.square(distances / influence_radii[None, :])).astype(np.float32)
        if bone_count > self.MAX_INFLUENCES:
            top_indices = np.argpartition(weights, -self.MAX_INFLUENCES, axis=1)[:, -self.MAX_INFLUENCES:]
            filtered = np.zeros_like(weights)
            row_indices = np.arange(vertex_count)[:, None]
            filtered[row_indices, top_indices] = weights[row_indices, top_indices]
            weights = filtered

        weight_sums = np.sum(weights, axis=1, keepdims=True)
        weight_sums[weight_sums < 1e-6] = 1.0
        weights = (weights / weight_sums).astype(np.float32)
        assignments, blends = self._build_vertex_regions(distances)
        return weights, segment_params, segment_offsets, assignments, blends

    def _build_vertex_regions(self, distances: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        chain_distances = []
        for chain_id, bone_indices in enumerate(self._chain_bone_indices):
            if len(bone_indices) == 0:
                chain_distances.append(np.full(len(distances), 1e6, dtype=np.float32))
            else:
                chain_distances.append(np.min(distances[:, bone_indices], axis=1).astype(np.float32))
        chain_distances = np.stack(chain_distances, axis=1).astype(np.float32)
        closest_chain = np.argmin(chain_distances, axis=1).astype(np.int32)
        closest_distance = chain_distances[np.arange(len(chain_distances)), closest_chain]

        assignments = np.full(len(self.neutral_vertices), -1, dtype=np.int32)
        blends = np.zeros(len(self.neutral_vertices), dtype=np.float32)

        non_thumb_root = float(np.min(self._neutral_landmarks[[5, 9, 13, 17], 1])) + 0.04
        thumb_distance_limit = 0.18
        finger_distance_limit = 0.18

        thumb_mask = (
            (closest_chain == self.THUMB_CHAIN_ID)
            & (closest_distance <= thumb_distance_limit)
            & (self.neutral_vertices[:, 0] <= -0.08)
            & (self.neutral_vertices[:, 1] >= 0.18)
        )
        assignments[thumb_mask] = self.THUMB_CHAIN_ID
        thumb_blend = np.minimum(
            _smoothstep(-0.18, -0.52, self.neutral_vertices[:, 0]),
            _smoothstep(0.20, 0.70, self.neutral_vertices[:, 1]),
        ).astype(np.float32)
        blends[thumb_mask] = np.maximum(thumb_blend[thumb_mask], 0.55)

        finger_mask = (
            (closest_chain != self.THUMB_CHAIN_ID)
            & (closest_distance <= finger_distance_limit)
            & (self.neutral_vertices[:, 1] >= non_thumb_root)
        )
        assignments[finger_mask] = closest_chain[finger_mask]
        finger_blend = _smoothstep(non_thumb_root, non_thumb_root + 0.34, self.neutral_vertices[:, 1]).astype(np.float32)
        blends[finger_mask] = np.maximum(finger_blend[finger_mask], 0.52)

        return assignments, blends

    def _palm_transform(self, solved_landmarks: np.ndarray) -> np.ndarray:
        neutral_x, neutral_y, neutral_z = self._solver.palm_basis(self._neutral_landmarks)
        current_x, current_y, current_z = self._solver.palm_basis(solved_landmarks)
        neutral_basis = np.stack((neutral_x, neutral_y, neutral_z), axis=1).astype(np.float32)
        current_basis = np.stack((current_x, current_y, current_z), axis=1).astype(np.float32)
        return neutral_basis @ current_basis.T

    def deform(self, solved_landmarks: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        solved_landmarks = np.asarray(solved_landmarks, dtype=np.float32)
        current_starts = solved_landmarks[self._bone_indices[:, 0]]
        current_ends = solved_landmarks[self._bone_indices[:, 1]]
        current_segments = current_ends - current_starts
        rotations = np.stack(
            [
                _rotation_matrix_from_vectors(self._neutral_directions[index], current_segments[index])
                for index in range(len(self._bone_indices))
            ],
            axis=0,
        ).astype(np.float32)

        palm_rotation = self._palm_transform(solved_landmarks)
        palm_vertices = (
            (self.neutral_vertices - self._neutral_landmarks[0][None, :]) @ palm_rotation
        ) + solved_landmarks[0][None, :]
        hand_base_vertices = (
            (self.neutral_vertices * (1.0 - self._forearm_blend[:, None]))
            + (palm_vertices * self._forearm_blend[:, None])
        ).astype(np.float32)
        vertices = hand_base_vertices.copy()

        for chain_id, bone_indices in enumerate(self._chain_bone_indices):
            mask = self._vertex_chain_assignments == chain_id
            if not np.any(mask):
                continue
            local_weights = self._vertex_weights[mask][:, bone_indices]
            local_weights = np.square(local_weights).astype(np.float32)
            if local_weights.shape[1] > 2:
                top_indices = np.argpartition(local_weights, -2, axis=1)[:, -2:]
                filtered = np.zeros_like(local_weights)
                row_indices = np.arange(len(local_weights))[:, None]
                filtered[row_indices, top_indices] = local_weights[row_indices, top_indices]
                local_weights = filtered
            local_weight_sums = np.sum(local_weights, axis=1, keepdims=True)
            local_weight_sums[local_weight_sums < 1e-6] = 1.0
            local_weights = (local_weights / local_weight_sums).astype(np.float32)

            closest_points = current_starts[None, bone_indices, :] + (
                self._vertex_segment_params[mask][:, bone_indices, None] * current_segments[None, bone_indices, :]
            )
            rotated_offsets = np.einsum(
                "bij,nbj->nbi",
                rotations[bone_indices],
                self._vertex_segment_offsets[mask][:, bone_indices, :],
                optimize=True,
            )
            transformed = closest_points + rotated_offsets
            chain_vertices = np.sum(transformed * local_weights[:, :, None], axis=1).astype(np.float32)

            blend = self._vertex_chain_blends[mask][:, None]
            vertices[mask] = (hand_base_vertices[mask] * (1.0 - blend)) + (chain_vertices * blend)

        normals = _recompute_vertex_normals(vertices, self.faces)
        anchors = solved_landmarks.astype(np.float32).copy()
        return vertices, normals, anchors


class HandPoseDisplayMapper:
    """Maps saved gesture-template landmarks into the Blender-hand display space and back."""

    def __init__(self, manifest: HandEditorAssetManifest):
        reference_templates = build_preview_templates()
        storage_reference = reference_templates["switch_to_keyboard"].as_array()
        self._forward = self._build_mapper(storage_reference, manifest.neutral_landmarks)
        self._inverse = self._build_mapper(manifest.neutral_landmarks, storage_reference)

    def _build_mapper(self, source_points: np.ndarray, target_points: np.ndarray):
        source_points = np.asarray(source_points, dtype=np.float32)
        target_points = np.asarray(target_points, dtype=np.float32)
        count = len(source_points)
        kernel = _rbf_kernel(_pairwise_distances(source_points, source_points))
        kernel += np.eye(count, dtype=np.float32) * 1e-5
        polynomial = np.concatenate(
            (
                np.ones((count, 1), dtype=np.float32),
                source_points,
            ),
            axis=1,
        )
        system = np.zeros((count + 4, count + 4), dtype=np.float32)
        system[:count, :count] = kernel
        system[:count, count:] = polynomial
        system[count:, :count] = polynomial.T
        inverse = np.linalg.inv(system).astype(np.float32)

        rhs = np.zeros((count + 4, 3), dtype=np.float32)
        rhs[:count, :] = target_points
        coefficients = inverse @ rhs

        def _map(points: np.ndarray) -> np.ndarray:
            points = np.asarray(points, dtype=np.float32)
            kernel_values = _rbf_kernel(_pairwise_distances(points, source_points))
            polynomial_values = np.concatenate(
                (
                    np.ones((len(points), 1), dtype=np.float32),
                    points,
                ),
                axis=1,
            )
            basis = np.concatenate((kernel_values, polynomial_values), axis=1)
            return (basis @ coefficients).astype(np.float32)

        return _map

    def to_display(self, landmarks: np.ndarray) -> np.ndarray:
        landmarks = np.asarray(landmarks, dtype=np.float32)
        return self._forward(landmarks)

    def to_storage(self, landmarks: np.ndarray) -> np.ndarray:
        landmarks = np.asarray(landmarks, dtype=np.float32)
        return self._inverse(landmarks)
