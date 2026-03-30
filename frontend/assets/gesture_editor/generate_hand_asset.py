from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parent
ASSET_PATH = ROOT / "hand_meshes.npz"
MANIFEST_PATH = ROOT / "hand_manifest.json"
LICENSE_PATH = ROOT / "LICENSE.txt"
SOURCE_MODEL_PATH = ROOT / "right_hand_empty_points.gltf"

LANDMARK_NAMES = [
    "Wrist",
    "Thumb CMC",
    "Thumb MCP",
    "Thumb IP",
    "Thumb Tip",
    "Index MCP",
    "Index PIP",
    "Index DIP",
    "Index Tip",
    "Middle MCP",
    "Middle PIP",
    "Middle DIP",
    "Middle Tip",
    "Ring MCP",
    "Ring PIP",
    "Ring DIP",
    "Ring Tip",
    "Pinky MCP",
    "Pinky PIP",
    "Pinky DIP",
    "Pinky Tip",
]

LANDMARK_CONNECTIONS = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (0, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (0, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (0, 17),
    (17, 18),
    (18, 19),
    (19, 20),
]

ANCHOR_NAMES = [
    "Anchor_00_Wrist",
    "Anchor_01_Thumb_CMC",
    "Anchor_02_Thumb_MCP",
    "Anchor_03_Thumb_IP",
    "Anchor_04_Thumb_Tip",
    "Anchor_05_Index_MCP",
    "Anchor_06_Index_PIP",
    "Anchor_07_Index_DIP",
    "Anchor_08_Index_Tip",
    "Anchor_09_Middle_MCP",
    "Anchor_10_Middle_PIP",
    "Anchor_11_Middle_DIP",
    "Anchor_12_Middle_Tip",
    "Anchor_13_Ring_MCP",
    "Anchor_14_Ring_PIP",
    "Anchor_15_Ring_DIP",
    "Anchor_16_Ring_Tip",
    "Anchor_17_Pinky_MCP",
    "Anchor_18_Pinky_PIP",
    "Anchor_19_Pinky_DIP",
    "Anchor_20_Pinky_Tip",
]


def _safe_unit(vector: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        return np.asarray(fallback, dtype=np.float32)
    return (vector / norm).astype(np.float32)


def _mesh_payload(mesh: trimesh.Trimesh) -> dict[str, np.ndarray]:
    return {
        "vertices": np.asarray(mesh.vertices, dtype=np.float32),
        "normals": np.asarray(mesh.vertex_normals, dtype=np.float32),
        "indices": np.asarray(mesh.faces.reshape(-1), dtype=np.uint32),
    }


def _extract_scene_data(source_path: Path) -> tuple[str, trimesh.Trimesh, np.ndarray]:
    scene = trimesh.load(str(source_path), force="scene")
    if not scene.geometry:
        raise ValueError(f"No geometry found in {source_path.name}")

    mesh_node_name = None
    mesh_geometry_name = None
    mesh_transform = None

    preferred_node = "Hand.R.003"
    if preferred_node in scene.graph.nodes:
        mesh_transform, mesh_geometry_name = scene.graph.get(preferred_node)
        if mesh_geometry_name is not None:
            mesh_node_name = preferred_node

    if mesh_node_name is None:
        for node_name in scene.graph.nodes:
            transform, geometry_name = scene.graph.get(node_name)
            if geometry_name is not None:
                mesh_node_name = str(node_name)
                mesh_geometry_name = str(geometry_name)
                mesh_transform = transform
                break

    if mesh_node_name is None or mesh_geometry_name is None or mesh_transform is None:
        raise ValueError(f"No mesh node found in {source_path.name}")

    base_mesh = scene.geometry[mesh_geometry_name].copy()
    base_mesh.apply_transform(mesh_transform)

    anchor_positions = []
    missing = []
    for anchor_name in ANCHOR_NAMES:
        if anchor_name not in scene.graph.nodes:
            missing.append(anchor_name)
            continue
        transform, _geometry_name = scene.graph.get(anchor_name)
        anchor_positions.append(np.asarray(transform[:3, 3], dtype=np.float32))

    if missing:
        raise ValueError(f"Missing required anchors: {', '.join(missing)}")

    return mesh_node_name, base_mesh, np.asarray(anchor_positions, dtype=np.float32)


def _canonicalize(mesh: trimesh.Trimesh, anchors: np.ndarray) -> tuple[trimesh.Trimesh, np.ndarray]:
    wrist = anchors[0]
    middle_mcp = anchors[9]
    index_mcp = anchors[5]
    pinky_mcp = anchors[17]
    thumb_cmc = anchors[1]

    y_axis = _safe_unit(middle_mcp - wrist, np.asarray((0.0, 1.0, 0.0), dtype=np.float32))
    x_seed = pinky_mcp - index_mcp
    x_axis = x_seed - (y_axis * float(np.dot(x_seed, y_axis)))
    x_axis = _safe_unit(x_axis, np.asarray((1.0, 0.0, 0.0), dtype=np.float32))
    if float(np.dot(thumb_cmc - wrist, x_axis)) > 0.0:
        x_axis *= -1.0
    z_axis = _safe_unit(np.cross(x_axis, y_axis), np.asarray((0.0, 0.0, 1.0), dtype=np.float32))
    y_axis = _safe_unit(np.cross(z_axis, x_axis), y_axis)

    basis = np.stack((x_axis, y_axis, z_axis), axis=1).astype(np.float32)
    scale = float(np.linalg.norm(middle_mcp - wrist))
    if scale < 1e-6:
        raise ValueError("Anchor_09_Middle_MCP is too close to the wrist to normalize the hand asset")

    canonical_vertices = ((np.asarray(mesh.vertices, dtype=np.float32) - wrist[None, :]) @ basis) / scale
    canonical_anchors = ((anchors - wrist[None, :]) @ basis) / scale

    canonical_mesh = mesh.copy()
    canonical_mesh.vertices = canonical_vertices.astype(np.float32)
    return canonical_mesh, canonical_anchors.astype(np.float32)


def _build_interaction_mesh(display_mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    # The interaction mesh is currently only used as a cheaper deformation basis.
    # Keep it identical to the display mesh for now to avoid introducing topology
    # damage from aggressive simplification.
    return display_mesh.copy()


def _segment_radii(anchors: np.ndarray) -> list[float]:
    radii = []
    for start, end in LANDMARK_CONNECTIONS:
        length = float(np.linalg.norm(anchors[end] - anchors[start]))
        radii.append(max(0.035, min(0.14, length * 0.28)))
    return radii


def _write_mesh_asset(meshes: dict[str, trimesh.Trimesh]):
    payload: dict[str, np.ndarray] = {}
    for prefix, mesh in meshes.items():
        mesh_data = _mesh_payload(mesh)
        for key, value in mesh_data.items():
            payload[f"{prefix}_{key}"] = value
    np.savez(ASSET_PATH, **payload)


def _write_manifest(mesh_node_name: str, neutral_anchors: np.ndarray):
    radii = _segment_radii(neutral_anchors)
    payload = {
        "version": 3,
        "editor_asset_version": "clean-rigged-hand-export-v1",
        "asset_file": "hand_meshes.npz",
        "mesh_asset_keys": {
            "display_hand": "DisplayHand",
            "interaction_hand": "InteractionHand",
        },
        "neutral_landmarks": [[float(x), float(y), float(z)] for x, y, z in neutral_anchors],
        "neutral_anchor_positions": [[float(x), float(y), float(z)] for x, y, z in neutral_anchors],
        "mesh_nodes": {
            "display_hand": mesh_node_name,
            "interaction_hand": f"{mesh_node_name}_Interaction",
        },
        "bone_nodes": [
            {
                "name": f"Segment_{start}_{end}",
                "start": start,
                "end": end,
                "radius": float(radius),
            }
            for (start, end), radius in zip(LANDMARK_CONNECTIONS, radii)
        ],
        "anchor_nodes": {str(index): name for index, name in enumerate(ANCHOR_NAMES)},
        "coordinate_space": {
            "source_asset": SOURCE_MODEL_PATH.name,
            "up_axis": "y",
            "forward_axis": "z",
        },
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_license():
    LICENSE_PATH.write_text(
        "This editor asset pack is derived from \"Hand Rig\"\n"
        "(https://sketchfab.com/3d-models/hand-rig-a348cf6087eb4fd98a83b026593823ad)\n"
        "by CreativeMachine (https://sketchfab.com/CreativeMachine), licensed under CC-BY-4.0.\n"
        "Retain attribution when redistributing this asset or derivatives of it.\n",
        encoding="utf-8",
    )


def main():
    if not SOURCE_MODEL_PATH.exists():
        raise SystemExit(f"Missing source hand asset: {SOURCE_MODEL_PATH}")

    mesh_node_name, source_mesh, source_anchors = _extract_scene_data(SOURCE_MODEL_PATH)
    display_mesh, neutral_anchors = _canonicalize(source_mesh, source_anchors)
    interaction_mesh = _build_interaction_mesh(display_mesh)

    ROOT.mkdir(parents=True, exist_ok=True)
    _write_mesh_asset(
        {
            "DisplayHand": display_mesh,
            "InteractionHand": interaction_mesh,
        }
    )
    _write_manifest(mesh_node_name, neutral_anchors)
    _write_license()
    print(f"Wrote {ASSET_PATH}")
    print(f"Wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
