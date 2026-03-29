from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QByteArray, QEvent, QRect, Qt, QPointF, Signal
from PySide6.QtGui import QColor, QVector3D, QPainter, QBrush, QPen, QQuaternion
from PySide6.Qt3DCore import Qt3DCore
from PySide6.Qt3DExtras import Qt3DExtras
from PySide6.Qt3DRender import Qt3DRender
from PySide6.QtWidgets import QVBoxLayout, QWidget

from backend.gesture_remap.hand_rig import (
    HAND_LANDMARK_COUNT,
    HandEditorAssetManifest,
    HandMeshDeformer,
    HandRigSolver,
    build_hand_assets,
    load_hand_mesh_assets,
)


def _safe_unit(vector: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        if fallback is None:
            return np.zeros(3, dtype=np.float32)
        return np.asarray(fallback, dtype=np.float32)
    return (vector / norm).astype(np.float32)


def _to_qvector3d(vector: np.ndarray | tuple[float, float, float]) -> QVector3D:
    x, y, z = [float(value) for value in vector]
    return QVector3D(x, y, z)


def _rotation_from_y(direction: np.ndarray) -> QQuaternion:
    target = _to_qvector3d(_safe_unit(direction, fallback=np.asarray((0.0, 1.0, 0.0), dtype=np.float32)))
    return QQuaternion.rotationTo(QVector3D(0.0, 1.0, 0.0), target)


def _rotation_from_basis(x_axis: np.ndarray, y_axis: np.ndarray) -> QQuaternion:
    local_x = np.asarray((1.0, 0.0, 0.0), dtype=np.float32)
    local_y = np.asarray((0.0, 1.0, 0.0), dtype=np.float32)
    target_y = _safe_unit(y_axis, fallback=local_y)
    rotation_primary = QQuaternion.rotationTo(_to_qvector3d(local_y), _to_qvector3d(target_y))
    rotated_x = rotation_primary.rotatedVector(_to_qvector3d(local_x))
    current_x = np.asarray((rotated_x.x(), rotated_x.y(), rotated_x.z()), dtype=np.float32)
    desired_x = _safe_unit(x_axis - (target_y * float(np.dot(x_axis, target_y))), fallback=current_x)
    current_x = _safe_unit(current_x - (target_y * float(np.dot(current_x, target_y))), fallback=desired_x)
    cross = np.cross(current_x, desired_x)
    dot = float(np.clip(np.dot(current_x, desired_x), -1.0, 1.0))
    angle = math.degrees(math.acos(dot))
    sign = 1.0 if float(np.dot(cross, target_y)) >= 0.0 else -1.0
    rotation_twist = QQuaternion.fromAxisAndAngle(_to_qvector3d(target_y), angle * sign)
    return rotation_twist * rotation_primary


class _DynamicMeshGeometry:
    def __init__(self, parent, vertices: np.ndarray, normals: np.ndarray, indices: np.ndarray):
        self.geometry = Qt3DCore.QGeometry(parent)
        self.vertex_buffer = Qt3DCore.QBuffer(self.geometry)
        self.index_buffer = Qt3DCore.QBuffer(self.geometry)

        self.position_attribute = Qt3DCore.QAttribute(self.geometry)
        self.position_attribute.setName(Qt3DCore.QAttribute.defaultPositionAttributeName())
        self.position_attribute.setVertexBaseType(Qt3DCore.QAttribute.VertexBaseType.Float)
        self.position_attribute.setVertexSize(3)
        self.position_attribute.setAttributeType(Qt3DCore.QAttribute.AttributeType.VertexAttribute)
        self.position_attribute.setBuffer(self.vertex_buffer)
        self.position_attribute.setByteOffset(0)
        self.position_attribute.setByteStride(24)
        self.position_attribute.setCount(len(vertices))

        self.normal_attribute = Qt3DCore.QAttribute(self.geometry)
        self.normal_attribute.setName(Qt3DCore.QAttribute.defaultNormalAttributeName())
        self.normal_attribute.setVertexBaseType(Qt3DCore.QAttribute.VertexBaseType.Float)
        self.normal_attribute.setVertexSize(3)
        self.normal_attribute.setAttributeType(Qt3DCore.QAttribute.AttributeType.VertexAttribute)
        self.normal_attribute.setBuffer(self.vertex_buffer)
        self.normal_attribute.setByteOffset(12)
        self.normal_attribute.setByteStride(24)
        self.normal_attribute.setCount(len(vertices))

        self.index_attribute = Qt3DCore.QAttribute(self.geometry)
        self.index_attribute.setAttributeType(Qt3DCore.QAttribute.AttributeType.IndexAttribute)
        self.index_attribute.setVertexBaseType(Qt3DCore.QAttribute.VertexBaseType.UnsignedInt)
        self.index_attribute.setBuffer(self.index_buffer)
        self.index_attribute.setCount(len(indices))

        self.geometry.addAttribute(self.position_attribute)
        self.geometry.addAttribute(self.normal_attribute)
        self.geometry.addAttribute(self.index_attribute)

        self.renderer = Qt3DRender.QGeometryRenderer(parent)
        self.renderer.setPrimitiveType(Qt3DRender.QGeometryRenderer.PrimitiveType.Triangles)
        self.renderer.setGeometry(self.geometry)
        self.renderer.setVertexCount(len(indices))
        self.index_buffer.setData(QByteArray(np.asarray(indices, dtype=np.uint32).tobytes()))
        self.update(vertices, normals)

    def update(self, vertices: np.ndarray, normals: np.ndarray):
        interleaved = np.hstack((vertices.astype(np.float32), normals.astype(np.float32)))
        self.vertex_buffer.setData(QByteArray(interleaved.tobytes()))
        self.position_attribute.setCount(len(vertices))
        self.normal_attribute.setCount(len(vertices))


class _HandViewportOverlay(QWidget):
    landmark_selected = Signal(int)
    landmark_dragged = Signal(int, float, float, float)
    orbit_requested = Signal(float, float)
    zoom_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._projected_points: list[QPointF] = []
        self._connections: list[tuple[int, int]] = []
        self._world_points = np.zeros((0, 3), dtype=np.float32)
        self._selected_index = 0
        self._drag_index = -1
        self._dragging_handle = False
        self._drag_plane_point = np.zeros(3, dtype=np.float32)
        self._drag_plane_normal = np.asarray((0.0, 0.0, 1.0), dtype=np.float32)
        self._orbiting = False
        self._last_pos = QPointF()
        self._view_matrix = None
        self._projection_matrix = None

    def set_view_state(self, projected_points, world_points, selected_index, view_matrix, projection_matrix, connections):
        self._projected_points = [QPointF(float(x), float(y)) for x, y in projected_points]
        self._connections = [(int(start), int(end)) for start, end in connections]
        self._world_points = np.asarray(world_points, dtype=np.float32)
        self._selected_index = int(selected_index)
        self._view_matrix = view_matrix
        self._projection_matrix = projection_matrix
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(103, 144, 205, 210), 2))
        for start, end in self._connections:
            if start >= len(self._projected_points) or end >= len(self._projected_points):
                continue
            painter.drawLine(self._projected_points[start], self._projected_points[end])
        for index, point in enumerate(self._projected_points):
            selected = index == self._selected_index
            radius = 10 if selected else 7
            fill = QColor(255, 196, 118, 240) if selected else QColor(66, 171, 255, 220)
            edge = QColor(255, 255, 255, 240) if selected else QColor(20, 33, 49, 220)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(edge, 2))
            painter.drawEllipse(point, radius, radius)

    def _nearest_index(self, position: QPointF) -> int:
        best_index = -1
        best_distance = 26.0
        for index, point in enumerate(self._projected_points):
            distance = math.hypot(point.x() - position.x(), point.y() - position.y())
            if distance <= best_distance:
                best_distance = distance
                best_index = index
        return best_index

    def _viewport_rect(self) -> QRect:
        return QRect(0, 0, max(1, self.width()), max(1, self.height()))

    def _screen_ray(self, position: QPointF) -> tuple[np.ndarray, np.ndarray] | None:
        if self._view_matrix is None or self._projection_matrix is None:
            return None
        viewport = self._viewport_rect()
        near = QVector3D(position.x(), self.height() - position.y(), 0.0).unproject(
            self._view_matrix,
            self._projection_matrix,
            viewport,
        )
        far = QVector3D(position.x(), self.height() - position.y(), 1.0).unproject(
            self._view_matrix,
            self._projection_matrix,
            viewport,
        )
        origin = np.asarray((near.x(), near.y(), near.z()), dtype=np.float32)
        direction = _safe_unit(
            np.asarray((far.x() - near.x(), far.y() - near.y(), far.z() - near.z()), dtype=np.float32),
            fallback=np.asarray((0.0, 0.0, -1.0), dtype=np.float32),
        )
        return origin, direction

    def _intersect_drag_plane(self, position: QPointF) -> np.ndarray | None:
        ray = self._screen_ray(position)
        if ray is None:
            return None
        origin, direction = ray
        denominator = float(np.dot(direction, self._drag_plane_normal))
        if abs(denominator) < 1e-6:
            return None
        distance = float(np.dot(self._drag_plane_point - origin, self._drag_plane_normal) / denominator)
        return origin + (direction * distance)

    def mousePressEvent(self, event):
        if self.handle_mouse_press(QPointF(event.position()), event.button()):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.handle_mouse_move(QPointF(event.position())):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.handle_mouse_release(QPointF(event.position()), event.button()):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        self.handle_wheel(float(event.angleDelta().y()) / 120.0)
        event.accept()

    def handle_mouse_press(self, position: QPointF, button) -> bool:
        if button == Qt.LeftButton:
            index = self._nearest_index(position)
            if index >= 0:
                self._drag_index = index
                self._dragging_handle = True
                self._last_pos = position
                self._drag_plane_point = self._world_points[index].copy()
                ray = self._screen_ray(position)
                if ray is not None:
                    _origin, direction = ray
                    self._drag_plane_normal = direction
                self.landmark_selected.emit(index)
                return True
        if button == Qt.RightButton:
            self._orbiting = True
            self._last_pos = position
            return True
        return False

    def handle_mouse_move(self, position: QPointF) -> bool:
        if self._dragging_handle and self._drag_index >= 0:
            hit = self._intersect_drag_plane(position)
            if hit is not None:
                self.landmark_dragged.emit(self._drag_index, float(hit[0]), float(hit[1]), float(hit[2]))
            return True
        if self._orbiting:
            delta = position - self._last_pos
            self._last_pos = position
            self.orbit_requested.emit(float(delta.x()), float(delta.y()))
            return True
        return False

    def handle_mouse_release(self, _position: QPointF, button) -> bool:
        if button == Qt.LeftButton and self._dragging_handle:
            self._dragging_handle = False
            self._drag_index = -1
            return True
        if button == Qt.RightButton and self._orbiting:
            self._orbiting = False
            return True
        return False

    def handle_wheel(self, steps: float):
        self.zoom_requested.emit(steps)


class HandRigScene(QWidget):
    landmark_selected = Signal(int)
    landmark_dragged = Signal(int, float, float, float)
    asset_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manifest = HandEditorAssetManifest.load()
        self._solver = HandRigSolver(self._manifest)
        self._landmarks = self._manifest.neutral_landmarks.copy()
        self._selected_index = 0
        self._asset_error: str | None = None
        self._mesh_deformer: HandMeshDeformer | None = None
        self._visual_mesh: _DynamicMeshGeometry | None = None
        self._visual_mesh_transform: Qt3DCore.QTransform | None = None
        self._neutral_visual_vertices: np.ndarray | None = None
        self._neutral_visual_normals: np.ndarray | None = None
        self._display_connections: tuple[tuple[int, int], ...] = ()
        self._handle_transforms: list[Qt3DCore.QTransform] = []
        self._handle_entities: list[Qt3DCore.QEntity] = []
        self._latest_visual_vertices: np.ndarray | None = None
        self._display_anchor_positions = self._manifest.neutral_anchor_positions.copy()
        self._landmark_anchor_offsets = self._landmarks - self._display_anchor_positions
        self._camera_fitted = False
        self._camera_yaw = -22.0
        self._camera_pitch = -16.0
        self._camera_distance = 9.5
        self._camera_center = np.asarray((0.0, 2.2, 0.0), dtype=np.float32)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._window = Qt3DExtras.Qt3DWindow()
        self._window.defaultFrameGraph().setClearColor(QColor(24, 27, 34))
        self._window.installEventFilter(self)
        self._container = QWidget.createWindowContainer(self._window, self)
        self._container.setMouseTracking(True)
        self._container.installEventFilter(self)
        layout.addWidget(self._container, 1)

        self._root_entity = Qt3DCore.QEntity()
        self._window.setRootEntity(self._root_entity)

        self._light_entity = Qt3DCore.QEntity(self._root_entity)
        light = Qt3DRender.QPointLight(self._light_entity)
        light.setColor(QColor(243, 230, 214))
        light.setIntensity(0.58)
        self._light_entity.addComponent(light)
        light_transform = Qt3DCore.QTransform(self._light_entity)
        light_transform.setTranslation(QVector3D(3.2, 5.0, 8.0))
        self._light_entity.addComponent(light_transform)

        self._fill_entity = Qt3DCore.QEntity(self._root_entity)
        fill_light = Qt3DRender.QPointLight(self._fill_entity)
        fill_light.setColor(QColor(220, 228, 240))
        fill_light.setIntensity(0.24)
        self._fill_entity.addComponent(fill_light)
        fill_transform = Qt3DCore.QTransform(self._fill_entity)
        fill_transform.setTranslation(QVector3D(-4.2, 3.0, 3.4))
        self._fill_entity.addComponent(fill_transform)

        self._hand_material = Qt3DExtras.QPhongMaterial(self._root_entity)
        self._hand_material.setAmbient(QColor(140, 105, 84))
        self._hand_material.setDiffuse(QColor(205, 166, 132))
        self._hand_material.setSpecular(QColor(65, 55, 48))
        self._hand_material.setShininess(6.0)
        self._handle_material_selected = Qt3DExtras.QPhongMaterial(self._root_entity)
        self._handle_material_selected.setAmbient(QColor(232, 159, 66))
        self._handle_material_selected.setDiffuse(QColor(255, 203, 125))
        self._handle_material_default = Qt3DExtras.QPhongMaterial(self._root_entity)
        self._handle_material_default.setAmbient(QColor(49, 116, 171))
        self._handle_material_default.setDiffuse(QColor(74, 181, 255))

        self._overlay = _HandViewportOverlay(self._container)
        self._overlay.landmark_selected.connect(self._on_overlay_landmark_selected)
        self._overlay.landmark_dragged.connect(self._on_overlay_landmark_dragged)
        self._overlay.orbit_requested.connect(self._on_orbit_requested)
        self._overlay.zoom_requested.connect(self._on_zoom_requested)
        self._overlay.raise_()

        self._build_mesh_scene()
        self._configure_camera()
        self._apply_pose()

    @property
    def asset_error(self) -> str | None:
        return self._asset_error

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self._container.rect())
        self._update_overlay()

    def eventFilter(self, watched, event):
        container = getattr(self, "_container", None)
        window = getattr(self, "_window", None)
        if watched in tuple(obj for obj in (container, window) if obj is not None):
            event_type = event.type()
            if event_type == QEvent.Type.MouseButtonPress:
                if self._overlay.handle_mouse_press(QPointF(event.position()), event.button()):
                    return True
            elif event_type == QEvent.Type.MouseMove:
                if self._overlay.handle_mouse_move(QPointF(event.position())):
                    return True
            elif event_type == QEvent.Type.MouseButtonRelease:
                if self._overlay.handle_mouse_release(QPointF(event.position()), event.button()):
                    return True
            elif event_type == QEvent.Type.Wheel:
                self._overlay.handle_wheel(float(event.angleDelta().y()) / 120.0)
                return True
        return super().eventFilter(watched, event)

    def _build_mesh_scene(self):
        try:
            mesh_assets = load_hand_mesh_assets(self._manifest)
        except Exception as exc:
            self._asset_error = f"Failed to load hand mesh asset: {exc}"
            self.asset_failed.emit(self._asset_error)
            return

        try:
            display_asset, interaction_asset = build_hand_assets(self._manifest, mesh_assets)
        except Exception as exc:
            self._asset_error = f"Hand mesh asset manifest is invalid: {exc}"
            self.asset_failed.emit(self._asset_error)
            return

        visual_mesh = display_asset.mesh
        self._mesh_deformer = HandMeshDeformer(self._manifest, display_asset, interaction_asset)
        self._neutral_visual_vertices = np.asarray(visual_mesh.vertices, dtype=np.float32)
        self._neutral_visual_normals = np.asarray(visual_mesh.normals, dtype=np.float32)
        self._display_connections = tuple((bone.start, bone.end) for bone in self._manifest.bone_nodes)

        visual_entity = Qt3DCore.QEntity(self._root_entity)
        self._visual_mesh_transform = Qt3DCore.QTransform(visual_entity)
        self._visual_mesh = _DynamicMeshGeometry(
            visual_entity,
            visual_mesh.vertices,
            visual_mesh.normals,
            visual_mesh.indices,
        )
        visual_entity.addComponent(self._visual_mesh.renderer)
        visual_entity.addComponent(self._visual_mesh_transform)
        visual_entity.addComponent(self._hand_material)

        for index in range(HAND_LANDMARK_COUNT):
            entity = Qt3DCore.QEntity(self._root_entity)
            mesh = Qt3DExtras.QSphereMesh(entity)
            mesh.setRadius(0.040 if index == 0 else 0.032)
            transform = Qt3DCore.QTransform(entity)
            entity.addComponent(mesh)
            entity.addComponent(transform)
            entity.addComponent(self._handle_material_selected if index == 0 else self._handle_material_default)
            self._handle_transforms.append(transform)
            self._handle_entities.append(entity)

        self._asset_error = None

    def set_selected_landmark(self, index: int):
        self._selected_index = max(0, min(HAND_LANDMARK_COUNT - 1, int(index)))
        for handle_index, entity in enumerate(self._handle_entities):
            if handle_index == self._selected_index:
                if self._handle_material_selected not in entity.components():
                    if self._handle_material_default in entity.components():
                        entity.removeComponent(self._handle_material_default)
                    entity.addComponent(self._handle_material_selected)
            else:
                if self._handle_material_default not in entity.components():
                    if self._handle_material_selected in entity.components():
                        entity.removeComponent(self._handle_material_selected)
                    entity.addComponent(self._handle_material_default)
        self._update_overlay()

    @property
    def current_landmarks(self) -> np.ndarray:
        return self._landmarks.copy()

    def set_landmarks(
        self,
        landmarks: np.ndarray,
        edited_index: int | None = None,
        previous_landmarks: np.ndarray | None = None,
    ):
        self._landmarks = self._solver.solve_landmarks(
            np.asarray(landmarks, dtype=np.float32),
            edited_index=edited_index,
            previous_landmarks=previous_landmarks,
        )
        self._apply_pose()
        if not self._camera_fitted:
            self.fit_camera_to_geometry()
            self._camera_fitted = True

    def _configure_camera(self):
        camera = self._window.camera()
        camera.lens().setPerspectiveProjection(34.0, 16 / 9, 0.1, 100.0)
        yaw_radians = math.radians(self._camera_yaw)
        pitch_radians = math.radians(self._camera_pitch)
        offset = np.asarray(
            (
                math.sin(yaw_radians) * math.cos(pitch_radians),
                math.sin(-pitch_radians),
                math.cos(yaw_radians) * math.cos(pitch_radians),
            ),
            dtype=np.float32,
        ) * self._camera_distance
        position = self._camera_center + offset
        camera.setPosition(_to_qvector3d(position))
        camera.setViewCenter(_to_qvector3d(self._camera_center))
        self._update_overlay()

    def _on_orbit_requested(self, delta_x: float, delta_y: float):
        self._camera_yaw = max(-180.0, min(180.0, self._camera_yaw - (delta_x * 0.35)))
        self._camera_pitch = max(-60.0, min(35.0, self._camera_pitch - (delta_y * 0.35)))
        self._configure_camera()

    def _on_zoom_requested(self, delta_steps: float):
        self._camera_distance = max(3.4, min(14.0, self._camera_distance - (delta_steps * 0.32)))
        self._configure_camera()

    def orbit_by(self, delta_yaw: float = 0.0, delta_pitch: float = 0.0):
        self._camera_yaw = max(-180.0, min(180.0, self._camera_yaw + float(delta_yaw)))
        self._camera_pitch = max(-60.0, min(35.0, self._camera_pitch + float(delta_pitch)))
        self._configure_camera()

    def zoom_by(self, delta_steps: float):
        self._on_zoom_requested(float(delta_steps))

    def reset_view(self):
        self._camera_yaw = -22.0
        self._camera_pitch = -16.0
        self.fit_camera_to_geometry()

    def _on_overlay_landmark_selected(self, index: int):
        self.set_selected_landmark(index)
        self.landmark_selected.emit(index)

    def _on_overlay_landmark_dragged(self, index: int, x: float, y: float, z: float):
        anchor = np.asarray((x, y, z), dtype=np.float32)
        landmark = anchor + self._landmark_anchor_offsets[index]
        self.landmark_dragged.emit(index, float(landmark[0]), float(landmark[1]), float(landmark[2]))

    def _apply_pose(self):
        if self._asset_error is not None or self._visual_mesh is None or self._mesh_deformer is None:
            self._update_overlay()
            return

        deformed_vertices, deformed_normals, deformed_anchors = self._mesh_deformer.deform(self._landmarks)
        self._latest_visual_vertices = deformed_vertices
        self._display_anchor_positions = self._landmarks.copy()
        self._landmark_anchor_offsets = np.zeros_like(self._landmarks, dtype=np.float32)
        self._visual_mesh.update(deformed_vertices, deformed_normals)
        if self._visual_mesh_transform is not None:
            self._visual_mesh_transform.setTranslation(QVector3D())
            self._visual_mesh_transform.setRotation(QQuaternion())
            self._visual_mesh_transform.setScale(1.0)
        for index, transform in enumerate(self._handle_transforms):
            transform.setTranslation(_to_qvector3d(self._display_anchor_positions[index]))

        self._update_overlay()

    def fit_camera_to_geometry(self):
        if self._latest_visual_vertices is not None and len(self._latest_visual_vertices) > 0:
            minimum = np.minimum(
                np.min(self._latest_visual_vertices, axis=0),
                np.min(self._display_anchor_positions, axis=0),
            )
            maximum = np.maximum(
                np.max(self._latest_visual_vertices, axis=0),
                np.max(self._display_anchor_positions, axis=0),
            )
        else:
            minimum = np.min(self._display_anchor_positions, axis=0)
            maximum = np.max(self._display_anchor_positions, axis=0)

        extents = np.maximum(maximum - minimum, 1e-3)
        self._camera_center = ((minimum + maximum) * 0.5).astype(np.float32)
        vertical_fov = math.radians(34.0)
        aspect = max(float(self.width()) / max(1.0, float(self.height())), 1.0)
        horizontal_fov = 2.0 * math.atan(math.tan(vertical_fov / 2.0) * aspect)
        distance_vertical = (extents[1] * 0.62) / max(math.tan(vertical_fov / 2.0), 1e-3)
        distance_horizontal = (extents[0] * 0.58) / max(math.tan(horizontal_fov / 2.0), 1e-3)
        self._camera_distance = max(5.2, min(18.0, max(distance_vertical, distance_horizontal) * 1.08))
        self._configure_camera()

    def _update_overlay(self):
        self._overlay.setGeometry(self._container.rect())
        camera = self._window.camera()
        view_matrix = camera.viewMatrix()
        projection_matrix = camera.projectionMatrix()
        viewport = QRect(0, 0, max(1, self._container.width()), max(1, self._container.height()))
        projected = []
        for point in self._display_anchor_positions:
            projected_point = QVector3D(float(point[0]), float(point[1]), float(point[2])).project(
                view_matrix,
                projection_matrix,
                viewport,
            )
            projected.append((projected_point.x(), self._container.height() - projected_point.y()))
        self._overlay.set_view_state(
            projected,
            self._display_anchor_positions,
            self._selected_index,
            view_matrix,
            projection_matrix,
            self._display_connections,
        )
