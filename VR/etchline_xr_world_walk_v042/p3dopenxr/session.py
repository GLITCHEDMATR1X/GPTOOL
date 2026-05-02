from __future__ import annotations

import ctypes
import logging
import platform

from direct.showbase.ShowBase import ShowBase
import xr

from .layer import ProjectionLayer
from .system import System


stringForFormat = {
    0x1907: 'RGB',
    0x1908: 'RGBA',
    0x8051: 'RGB8',
    0x8058: 'RGBA8',
    0x8C43: 'SRGB8',
    0x8C43 + 1: 'SRGB8_ALPHA8',
    0x881A: 'RGB16F',
    0x881B: 'RGBA16F',
    0x805B: 'RGB16',
    0x805B + 1: 'RGBA16',
}


class Session:
    def __init__(self, system: System, base: ShowBase):
        self.logger = logging.getLogger('session')
        self.handle = None
        self.system = system
        self.base = base
        self.state = xr.SessionState.IDLE
        self.frame_state = xr.FrameState()
        self.graphics_binding = None
        if platform.system() == 'Windows':
            from OpenGL import WGL

            self.graphics_binding = xr.GraphicsBindingOpenGLWin32KHR()
            self.graphics_binding.h_dc = WGL.wglGetCurrentDC()
            self.graphics_binding.h_glrc = WGL.wglGetCurrentContext()
        elif platform.system() == 'Linux':
            from OpenGL import GLX

            drawable = GLX.glXGetCurrentDrawable()
            context = GLX.glXGetCurrentContext()
            display = GLX.glXGetCurrentDisplay()
            self.graphics_binding = xr.GraphicsBindingOpenGLXlibKHR(
                x_display=display,
                glx_drawable=drawable,
                glx_context=context,
            )
        else:
            raise NotImplementedError(f'Unsupported platform {platform.system()}')
        graphics_binding_pointer = ctypes.cast(ctypes.pointer(self.graphics_binding), ctypes.c_void_p)
        session_create_info = xr.SessionCreateInfo(
            next=graphics_binding_pointer,
            create_flags=xr.SessionCreateFlags(),
            system_id=system.handle,
        )
        self.handle = xr.create_session(system.instance.handle, session_create_info)
        self.log_swapchain_formats()
        self.log_reference_spaces()

    def destroy(self):
        if self.handle is not None:
            try:
                xr.destroy_session(self.handle)
            finally:
                self.handle = None
                self.system = None

    def get_supported_swapchain_formats(self):
        return xr.enumerate_swapchain_formats(self.handle)

    def session_active(self):
        return self.state in (
            xr.SessionState.READY,
            xr.SessionState.SYNCHRONIZED,
            xr.SessionState.VISIBLE,
            xr.SessionState.FOCUSED,
        )

    def should_render(self):
        return bool(self.frame_state.should_render)

    def on_state_changed(self, session_state_changed_event):
        event = ctypes.cast(
            ctypes.byref(session_state_changed_event), ctypes.POINTER(xr.EventDataSessionStateChanged)
        ).contents
        old_state = self.state
        self.state = xr.SessionState(event.state)
        self.logger.info('Session state %s -> %s', old_state, self.state)
        if self.state == xr.SessionState.READY:
            if self.handle is not None:
                xr.begin_session(self.handle, xr.SessionBeginInfo(self.system.view_configuration_type))
        elif self.state == xr.SessionState.STOPPING:
            xr.end_session(self.handle)
        elif self.state in (xr.SessionState.EXITING, xr.SessionState.LOSS_PENDING):
            self.base.userExit()

    def poll_xr_events(self):
        while True:
            try:
                event_buffer = xr.poll_event(self.system.instance.handle)
                event_type = xr.StructureType(event_buffer.type)
                if event_type == xr.StructureType.EVENT_DATA_EVENTS_LOST:
                    events_lost = ctypes.cast(event_buffer, ctypes.POINTER(xr.EventDataEventsLost))
                    self.logger.warning('%s events lost', events_lost)
                elif event_type == xr.StructureType.EVENT_DATA_INSTANCE_LOSS_PENDING:
                    self.logger.warning('Instance loss pending at %s', event_buffer.loss_time)
                    self.base.userExit()
                elif event_type == xr.StructureType.EVENT_DATA_SESSION_STATE_CHANGED:
                    self.on_state_changed(event_buffer)
                else:
                    self.logger.debug('Ignoring event type %s', event_type)
            except xr.EventUnavailable:
                break

    def wait_frame(self):
        if not self.session_active():
            return
        self.frame_state = xr.wait_frame(self.handle, xr.FrameWaitInfo(None))

    def begin_frame(self):
        if not self.session_active():
            return
        xr.begin_frame(self.handle, xr.FrameBeginInfo())

    def end_frame(self, layer: ProjectionLayer):
        if not self.session_active():
            return
        layers = []
        if self.should_render() and layer.layer_valid():
            layers.append(ctypes.byref(layer.handle))
        frame_end_info = xr.FrameEndInfo(
            self.frame_state.predicted_display_time,
            xr.EnvironmentBlendMode.OPAQUE,
            layers=layers,
        )
        xr.end_frame(self.handle, frame_end_info)

    def log_reference_spaces(self):
        spaces = xr.enumerate_reference_spaces(self.handle)
        self.logger.info('Available reference spaces: %d', len(spaces))
        for space in spaces:
            self.logger.debug('  Name: %s', xr.ReferenceSpaceType(space))

    def log_swapchain_formats(self) -> None:
        formats = list(self.get_supported_swapchain_formats())
        if not formats:
            self.logger.warning('Runtime returned no swapchain formats.')
            return
        pretty = [stringForFormat.get(int(sc_format), hex(int(sc_format))) for sc_format in formats]
        self.logger.info('Supported swapchain formats: %s', ', '.join(pretty))
