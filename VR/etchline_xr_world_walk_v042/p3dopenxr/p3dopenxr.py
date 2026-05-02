from __future__ import annotations

import atexit
from functools import partial
import logging

from direct.task.TaskManagerGlobal import taskMgr
from OpenGL import GL
from panda3d.core import Camera, FrameBufferProperties, LMatrix4, MatrixLens, NodePath, PythonCallbackObject
import xr

from .actionset import ActionSet
from .diagnostics import XRPoseSnapshot, XRRuntimeDiagnostics
from .instance import Instance, _xr_text
from .layer import ProjectionLayer
from .pose import xr_pose_to_panda
from .session import Session
from .space import Space
from .swapchain import Swapchain
from .system import System
from .version import __version__

logging.basicConfig(level=logging.INFO)

class P3DOpenXR:
    def __init__(self, base=None):
        self.logger = logging.getLogger('p3dopenxr')
        if base is None:
            base = __builtins__.get('base')
        self.base = base
        self.buffers = []
        self.cams = []
        self.dr = []
        self.tasks = []
        self.nextsort = self.base.win.getSort() - 1000
        self.instance = None
        self.system = None
        self.session = None
        self.action_set = None
        self.app_space = None
        self.tracking_space = None
        self.view_space = None
        self.swapchains = []
        self.layer = None
        self.end_frame_called = False
        self.frame_index = 0
        self.near = 0.01
        self.far = 100.0
        self.mirroring = 0
        self.mirror_mode = 'average'
        self.empty_world = None
        self.tracking_space_anchor = None
        self.hmd_anchor = None
        self.left_eye_anchor = None
        self.right_eye_anchor = None
        self.left_grip_anchor = None
        self.right_grip_anchor = None
        self.left_aim_anchor = None
        self.right_aim_anchor = None
        self.left_hand_anchor = None
        self.right_hand_anchor = None
        self.hmd_pose_valid = False
        atexit.register(self.destroy)

    def create_default_fb_props(self):
        props = FrameBufferProperties(FrameBufferProperties.get_default())
        props.set_back_buffers(0)
        props.set_rgb_color(1)
        props.set_alpha_bits(8)
        props.set_srgb_color(True)
        props.set_depth_bits(24)
        return props

    def create_buffer(self, name, width, height, fb_props):
        buffer = self.base.win.make_texture_buffer(name, width, height, to_ram=False, fbp=fb_props)
        if buffer is not None:
            buffer.disable_clears()
            buffer.set_active(True)
            buffer.clear_render_textures()
            buffer.set_sort(self.nextsort)
            self.nextsort += 1
        else:
            self.logger.error('Could not create buffer %s', name)
        return buffer

    def create_display_region(self, buffer, camera, callback, cc=None):
        dr = buffer.make_display_region(0, 1, 0, 1)
        dr.set_camera(camera)
        dr.set_active(1)
        dr.disable_clears()
        if callback is not None:
            dr.set_draw_callback(PythonCallbackObject(callback))
        if cc is not None:
            dr.set_clear_color_active(1)
            dr.set_clear_color(cc)
        return dr

    def create_camera(self, name: str) -> Camera:
        cam_node = Camera(name)
        lens = MatrixLens()
        lens.set_user_mat(LMatrix4())
        cam_node.set_lens(lens)
        return cam_node

    def disable_main_cam(self):
        self.empty_world = NodePath('xr-empty-world')
        self.base.camera.reparent_to(self.empty_world)

    def enable_mirror_camera(self):
        self.base.camera.reparent_to(self.tracking_space_anchor)
        mirror_lens = self.base.cam.node().get_lens()
        if not isinstance(mirror_lens, MatrixLens):
            mirror_lens = MatrixLens()
            mirror_lens.set_user_mat(LMatrix4())
            self.base.cam.node().set_lens(mirror_lens)
        mirror_lens.set_near_far(self.near, self.far)

    def choose_swapchain_format(self, requested_format: int) -> int:
        supported_formats = list(self.session.get_supported_swapchain_formats())
        if not supported_formats:
            self.logger.warning('Runtime reported no swapchain formats; using requested format %s', hex(requested_format))
            return requested_format

        candidates = []
        def add_candidate(value: int | None) -> None:
            if value is None:
                return
            if value not in candidates:
                candidates.append(value)

        add_candidate(requested_format)
        for fmt in (
            GL.GL_SRGB8_ALPHA8,
            GL.GL_RGBA8,
            getattr(GL, 'GL_RGBA8_SNORM', None),
            GL.GL_RGBA16F,
            GL.GL_RGB10_A2,
            GL.GL_SRGB8,
            GL.GL_RGB8,
            GL.GL_R11F_G11F_B10F,
            GL.GL_RGB16F,
            GL.GL_RGBA16,
            GL.GL_RGBA,
            GL.GL_RGB,
        ):
            add_candidate(fmt)

        supported_set = set(int(fmt) for fmt in supported_formats)
        for fmt in candidates:
            if int(fmt) in supported_set:
                if int(fmt) != int(requested_format):
                    self.logger.warning(
                        'Requested swapchain format %s unsupported; falling back to %s',
                        hex(int(requested_format)),
                        hex(int(fmt)),
                    )
                else:
                    self.logger.info('Using swapchain format %s', hex(int(fmt)))
                return int(fmt)

        fallback = int(supported_formats[0])
        self.logger.warning(
            'No preferred swapchain format matched runtime list; using first supported format %s',
            hex(fallback),
        )
        return fallback

    def init(self, near=0.01, far=100.0, root=None, fb_props=None, mirroring=1, mirror_mode='average'):
        if fb_props is None:
            fb_props = self.create_default_fb_props()
        self.near = near
        self.far = far
        self.mirroring = mirroring
        self.mirror_mode = mirror_mode
        self.instance = Instance(application_name='ChamelionPixels XR Lab')
        self.system = System(self.instance)
        self.session = Session(self.system, self.base)
        requested_sc_format = self.fb_props_to_gl_mode(fb_props)
        sc_format = self.choose_swapchain_format(requested_sc_format)
        self.tracking_space = Space.create_best(self.session, preferred=('Stage', 'Local'))
        self.view_space = Space(self.session, reference_space_type='View')
        self.app_space = self.tracking_space
        for view in self.system.views:
            self.swapchains.append(Swapchain(self.session, view, sc_format=sc_format, sample_count=1))
        self.layer = ProjectionLayer(self.session, self.app_space, len(self.system.views))
        self.action_set = ActionSet(self.session, self.app_space, 'default', 'Default action set', priority=0)

        if root is None:
            root = self.base.render
        self.tracking_space_anchor = root.attach_new_node('tracking-space-anchor')
        self.hmd_anchor = self.tracking_space_anchor.attach_new_node('hmd-anchor')
        self.left_eye_anchor = self.tracking_space_anchor.attach_new_node('left-eye-anchor')
        self.right_eye_anchor = self.tracking_space_anchor.attach_new_node('right-eye-anchor')
        self.left_grip_anchor = self.tracking_space_anchor.attach_new_node('left-grip-anchor')
        self.right_grip_anchor = self.tracking_space_anchor.attach_new_node('right-grip-anchor')
        self.left_aim_anchor = self.tracking_space_anchor.attach_new_node('left-aim-anchor')
        self.right_aim_anchor = self.tracking_space_anchor.attach_new_node('right-aim-anchor')
        self.left_hand_anchor = self.left_grip_anchor
        self.right_hand_anchor = self.right_grip_anchor

        for i, swapchain in enumerate(self.swapchains):
            cam_node = self.create_camera(f'cam-{i}')
            cam = self.tracking_space_anchor.attach_new_node(cam_node)
            self.cams.append(cam)
            buffer = self.create_buffer(f'xr-render-buffer-{i}', swapchain.width, swapchain.height, fb_props)
            last = i == len(self.swapchains) - 1
            self.dr.append(self.create_display_region(buffer, self.cams[i], callback=partial(self.render, i, last)))
            self.buffers.append(buffer)

        self.action_set.link_action_pose('grip_pose', 'left', self.left_grip_anchor)
        self.action_set.link_action_pose('grip_pose', 'right', self.right_grip_anchor)
        self.action_set.link_action_pose('aim_pose', 'left', self.left_aim_anchor)
        self.action_set.link_action_pose('aim_pose', 'right', self.right_aim_anchor)
        self.action_set.attach()

        if self.mirroring:
            self.enable_mirror_camera()
        else:
            self.disable_main_cam()

        self.tasks.append(taskMgr.add(self.poll_events_task, 'openXRPollEvents', sort=-1000))
        self.tasks.append(taskMgr.add(self.wait_frame_task, 'openXRWaitFrame', sort=-999))
        self.tasks.append(taskMgr.add(self.update_views_task, 'openXRUpdateViews', sort=-100))
        self.tasks.append(taskMgr.add(self.poll_actions_task, 'openXRPollActions', sort=-40))
        self.tasks.append(taskMgr.add(self.end_frame_task, 'openXREndFrame', sort=1000))

    def destroy(self):
        for task in self.tasks:
            try:
                task.remove()
            except Exception:
                pass
        self.tasks.clear()
        if self.action_set is not None:
            self.action_set.destroy()
            self.action_set = None
        if self.layer is not None:
            self.layer.destroy()
            self.layer = None
        for swapchain in self.swapchains:
            swapchain.destroy()
        self.swapchains.clear()
        if self.tracking_space is not None:
            self.tracking_space.destroy()
            self.tracking_space = None
        if self.view_space is not None:
            self.view_space.destroy()
            self.view_space = None
        if self.session is not None:
            self.session.destroy()
            self.session = None
        if self.system is not None:
            self.system.destroy()
            self.system = None
        if self.instance is not None:
            self.instance.destroy()
            self.instance = None

    def poll_events_task(self, task):
        self.session.poll_xr_events()
        return task.cont

    def wait_frame_task(self, task):
        if not self.session.session_active():
            return task.cont
        self.session.wait_frame()
        self.session.begin_frame()
        self.end_frame_called = False
        self.frame_index += 1
        return task.cont

    def _update_hmd_anchor(self) -> None:
        self.hmd_pose_valid = False
        if not self.session.session_active():
            return
        space_location = xr.locate_space(
            space=self.view_space.handle,
            base_space=self.app_space.handle,
            time=self.session.frame_state.predicted_display_time,
        )
        flags = space_location.location_flags
        pose_valid = (
            flags & xr.SPACE_LOCATION_POSITION_VALID_BIT != 0 and
            flags & xr.SPACE_LOCATION_ORIENTATION_VALID_BIT != 0
        )
        self.hmd_pose_valid = bool(pose_valid)
        if pose_valid:
            panda_pos, panda_quat = xr_pose_to_panda(space_location.pose.position, space_location.pose.orientation)
            self.hmd_anchor.set_pos(panda_pos)
            self.hmd_anchor.set_quat(panda_quat)

    def _update_mirror_camera(self, views):
        if not self.mirroring:
            return
        if self.mirror_mode == 'left' and views:
            view = views[0]
            self.base.cam.set_pos(view.position)
            self.base.cam.set_quat(view.orientation)
            self.base.cam.node().get_lens().set_user_mat(view.calc_projection_matrix(self.near, self.far))
            return
        if len(views) >= 2:
            left_view = views[0]
            right_view = views[1]
            self.base.cam.set_pos((left_view.position + right_view.position) * 0.5)
            self.base.cam.set_quat(self.hmd_anchor.get_quat(self.tracking_space_anchor))
            self.base.cam.node().get_lens().set_user_mat(left_view.calc_projection_matrix(self.near, self.far))
        elif views:
            self.base.cam.set_pos(views[0].position)
            self.base.cam.set_quat(views[0].orientation)
            self.base.cam.node().get_lens().set_user_mat(views[0].calc_projection_matrix(self.near, self.far))

    def update_views_task(self, task):
        if not self.session.session_active() or not self.session.should_render():
            return task.cont
        self.layer.update_views(self.swapchains)
        if not self.layer.pose_valid:
            return task.cont
        self._update_hmd_anchor()
        for cam, anchor, view in zip(self.cams, (self.left_eye_anchor, self.right_eye_anchor), self.layer.views):
            cam.node().get_lens().set_user_mat(view.calc_projection_matrix(self.near, self.far))
            cam.set_pos(view.position)
            cam.set_quat(view.orientation)
            anchor.set_pos(view.position)
            anchor.set_quat(view.orientation)
        self._update_mirror_camera(self.layer.views)
        return task.cont

    def poll_actions_task(self, task):
        try:
            self.action_set.poll_actions()
        except xr.exception.SessionNotFocused:
            pass
        return task.cont

    def render(self, index, last, cbdata):
        if not self.session.session_active() or not self.session.should_render() or not self.layer.pose_valid:
            return
        swapchain = self.swapchains[index]
        image_info = swapchain.acquire_image_info()
        self.layer.render_swapchain(index)
        GL.glFramebufferTexture(GL.GL_DRAW_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, image_info.image, 0)
        GL.glClearDepth(1.0)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT | GL.GL_STENCIL_BUFFER_BIT)
        cbdata.upcall()
        swapchain.release_image_info()
        if last:
            self.session.end_frame(self.layer)
            self.end_frame_called = True

    def end_frame_task(self, task):
        if not self.session.session_active():
            return task.cont
        if not self.end_frame_called:
            self.session.end_frame(self.layer)
            self.end_frame_called = True
        return task.cont

    def button(self, action_name: str, hand: str) -> bool:
        return self.action_set.get_bool(action_name, hand)

    def axis1d(self, action_name: str, hand: str) -> float:
        return self.action_set.get_float(action_name, hand)

    def axis2d(self, action_name: str, hand: str) -> tuple[float, float]:
        return self.action_set.get_vector2f(action_name, hand)

    def pulse(self, hand: str, amplitude: float = 0.4, duration_sec: float = 0.05, frequency: float = 0.0) -> None:
        self.action_set.apply_haptic(hand, amplitude=amplitude, duration_sec=duration_sec, frequency=frequency)

    def get_diagnostics(self) -> XRRuntimeDiagnostics:
        runtime_name = 'unknown'
        runtime_version = 'unknown'
        system_name = 'unknown'
        if self.instance is not None and getattr(self.instance, 'handle', None) is not None:
            try:
                props = xr.get_instance_properties(instance=self.instance.handle)
                runtime_name = _xr_text(props.runtime_name)
                runtime_version = str(xr.Version(props.runtime_version))
            except Exception:
                pass
        if self.system is not None:
            try:
                system_props = xr.get_system_properties(self.instance.handle, self.system.handle)
                system_name = _xr_text(system_props.system_name)
            except Exception:
                pass
        poses = [
            XRPoseSnapshot(
                name='hmd',
                valid=self.hmd_pose_valid,
                position=(self.hmd_anchor.get_x(), self.hmd_anchor.get_y(), self.hmd_anchor.get_z()),
                orientation=(
                    self.hmd_anchor.get_quat().get_r(),
                    self.hmd_anchor.get_quat().get_i(),
                    self.hmd_anchor.get_quat().get_j(),
                    self.hmd_anchor.get_quat().get_k(),
                ),
            ),
            XRPoseSnapshot(
                name='left_grip',
                valid=not self.left_grip_anchor.is_stashed(),
                position=(self.left_grip_anchor.get_x(), self.left_grip_anchor.get_y(), self.left_grip_anchor.get_z()),
                orientation=(
                    self.left_grip_anchor.get_quat().get_r(),
                    self.left_grip_anchor.get_quat().get_i(),
                    self.left_grip_anchor.get_quat().get_j(),
                    self.left_grip_anchor.get_quat().get_k(),
                ),
            ),
            XRPoseSnapshot(
                name='right_grip',
                valid=not self.right_grip_anchor.is_stashed(),
                position=(self.right_grip_anchor.get_x(), self.right_grip_anchor.get_y(), self.right_grip_anchor.get_z()),
                orientation=(
                    self.right_grip_anchor.get_quat().get_r(),
                    self.right_grip_anchor.get_quat().get_i(),
                    self.right_grip_anchor.get_quat().get_j(),
                    self.right_grip_anchor.get_quat().get_k(),
                ),
            ),
        ]
        return XRRuntimeDiagnostics(
            application_name=f'ChamelionPixels XR Lab {__version__}',
            runtime_name=runtime_name,
            runtime_version=runtime_version,
            system_name=system_name,
            session_state=str(self.session.state) if self.session is not None else 'unknown',
            tracking_space=str(getattr(self.tracking_space, 'reference_space_type', 'unknown')),
            session_active=self.session.session_active() if self.session is not None else False,
            should_render=self.session.should_render() if self.session is not None else False,
            frame_index=self.frame_index,
            headset_tracked=self.hmd_pose_valid,
            left_controller_tracked=not self.left_grip_anchor.is_stashed(),
            right_controller_tracked=not self.right_grip_anchor.is_stashed(),
            poses=poses,
            actions=self.action_set.diagnostics() if self.action_set is not None else [],
        )

    def fb_props_to_gl_mode(self, fb_props: FrameBufferProperties):
        if fb_props.alpha_bits == 0:
            if fb_props.srgb_color:
                gl_format = GL.GL_SRGB8
            elif (fb_props.color_bits > 16 * 3 or fb_props.red_bits > 16 or fb_props.green_bits > 16 or fb_props.blue_bits > 16):
                if fb_props.blue_bits > 0 or fb_props.color_bits == 1 or fb_props.color_bits > 32 * 2:
                    gl_format = GL.GL_RGB32F
                elif fb_props.green_bits > 0 or fb_props.color_bits > 32:
                    gl_format = GL.GL_RG32F
                else:
                    gl_format = GL.GL_R32F
            elif fb_props.float_color:
                if fb_props.blue_bits > 10 or fb_props.color_bits == 1 or fb_props.color_bits > 32:
                    gl_format = GL.GL_RGB16F
                elif fb_props.blue_bits > 0:
                    if fb_props.red_bits > 11 or fb_props.green_bits > 11:
                        gl_format = GL.GL_RGB16F
                    else:
                        gl_format = GL.GL_R11F_G11F_B10F
                elif fb_props.green_bits > 0 or fb_props.color_bits > 16:
                    gl_format = GL.GL_RG16F
                else:
                    gl_format = GL.GL_R16F
            elif (fb_props.color_bits > 10 * 3 or fb_props.red_bits > 10 or fb_props.green_bits > 10 or fb_props.blue_bits > 10):
                gl_format = GL.GL_RGB10_A2
            else:
                gl_format = GL.GL_RGB8
        else:
            if fb_props.srgb_color:
                gl_format = GL.GL_SRGB8_ALPHA8
            elif fb_props.float_color:
                gl_format = GL.GL_RGBA32F if fb_props.color_bits > 16 * 3 else GL.GL_RGBA16F
            else:
                if fb_props.color_bits > 16 * 3:
                    gl_format = GL.GL_RGBA32F
                elif fb_props.color_bits > 8 * 3:
                    gl_format = GL.GL_RGBA16
                else:
                    gl_format = GL.GL_RGBA8
        return gl_format
