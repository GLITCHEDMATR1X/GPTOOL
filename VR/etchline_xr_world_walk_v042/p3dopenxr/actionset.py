from __future__ import annotations

import ctypes
from dataclasses import dataclass
import logging
from typing import Any

from panda3d.core import NodePath
import xr

from .diagnostics import XRActionSnapshot
from .pose import xr_pose_to_panda

_HAND_PATHS = {
    'left': '/user/hand/left',
    'right': '/user/hand/right',
}


@dataclass(frozen=True)
class XRBinding:
    profile: str
    binding: str
    hand_aware: bool = True
    hands: tuple[str, ...] | None = None


@dataclass(frozen=True)
class XRActionDefinition:
    name: str
    localized_name: str
    action_type: str
    hands: tuple[str, ...] = ('left', 'right')
    bindings: tuple[XRBinding, ...] = ()


@dataclass
class XRActionState:
    action_name: str
    hand: str | None
    state_type: str
    is_active: bool = False
    changed_since_last_sync: bool = False
    current_state: Any = None
    pose_valid: bool = False
    tracked: bool = False

    def to_snapshot(self) -> XRActionSnapshot:
        return XRActionSnapshot(
            action_name=self.action_name,
            hand=self.hand,
            state_type=self.state_type,
            is_active=self.is_active,
            changed_since_last_sync=self.changed_since_last_sync,
            current_state=self.current_state,
            pose_valid=self.pose_valid,
            tracked=self.tracked,
        )


class ActionSet:
    def __init__(self, session, app_space, name: str, localized_name: str, priority: int = 0,
                 action_definitions: list[XRActionDefinition] | None = None):
        self.logger = logging.getLogger('actionset::' + name)
        self.session = session
        self.app_space = app_space
        self.pose_links: dict[tuple[str, str], NodePath] = {}
        self.actions: dict[str, xr.Action] = {}
        self.pose_spaces: dict[tuple[str, str], xr.Space] = {}
        self.states: dict[tuple[str, str | None], XRActionState] = {}
        self.subaction_paths = {
            hand: xr.string_to_path(self.session.system.instance.handle, path)
            for hand, path in _HAND_PATHS.items()
        }
        instance = self.session.system.instance
        action_set_info = xr.ActionSetCreateInfo(
            action_set_name=name,
            localized_action_set_name=localized_name,
            priority=priority,
        )
        self.handle = xr.create_action_set(instance.handle, action_set_info)
        if action_definitions is None:
            action_definitions = self.build_default_action_definitions()
        self.action_definitions = action_definitions
        self._create_actions()
        self._suggest_default_bindings()

    @staticmethod
    def build_default_action_definitions() -> list[XRActionDefinition]:
        return [
            XRActionDefinition(
                name='grip_pose',
                localized_name='Grip Pose',
                action_type='pose',
                bindings=(
                    XRBinding('/interaction_profiles/khr/simple_controller', '/user/hand/{hand}/input/grip/pose'),
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/input/grip/pose'),
                ),
            ),
            XRActionDefinition(
                name='aim_pose',
                localized_name='Aim Pose',
                action_type='pose',
                bindings=(
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/input/aim/pose'),
                ),
            ),
            XRActionDefinition(
                name='trigger_value',
                localized_name='Trigger Value',
                action_type='float',
                bindings=(
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/input/trigger/value'),
                ),
            ),
            XRActionDefinition(
                name='trigger_click',
                localized_name='Trigger Click',
                action_type='boolean',
                bindings=(
                    XRBinding('/interaction_profiles/khr/simple_controller', '/user/hand/{hand}/input/select/click'),
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/input/trigger/value'),
                ),
            ),
            XRActionDefinition(
                name='squeeze_value',
                localized_name='Squeeze Value',
                action_type='float',
                bindings=(
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/input/squeeze/value'),
                ),
            ),
            XRActionDefinition(
                name='thumbstick',
                localized_name='Thumbstick',
                action_type='vector2f',
                bindings=(
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/input/thumbstick/x'),
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/input/thumbstick/y'),
                ),
            ),
            XRActionDefinition(
                name='primary_button',
                localized_name='Primary Button',
                action_type='boolean',
                bindings=(
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/left/input/x/click', hand_aware=False, hands=('left',)),
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/right/input/a/click', hand_aware=False, hands=('right',)),
                ),
            ),
            XRActionDefinition(
                name='secondary_button',
                localized_name='Secondary Button',
                action_type='boolean',
                bindings=(
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/left/input/y/click', hand_aware=False, hands=('left',)),
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/right/input/b/click', hand_aware=False, hands=('right',)),
                ),
            ),
            XRActionDefinition(
                name='menu_click',
                localized_name='Menu Click',
                action_type='boolean',
                hands=('left',),
                bindings=(
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/left/input/menu/click', hand_aware=False),
                ),
            ),
            XRActionDefinition(
                name='haptic',
                localized_name='Haptic',
                action_type='vibration',
                bindings=(
                    XRBinding('/interaction_profiles/khr/simple_controller', '/user/hand/{hand}/output/haptic'),
                    XRBinding('/interaction_profiles/oculus/touch_controller', '/user/hand/{hand}/output/haptic'),
                ),
            ),
        ]

    def _xr_action_type(self, action_type: str):
        mapping = {
            'pose': 'POSE_INPUT',
            'boolean': 'BOOLEAN_INPUT',
            'float': 'FLOAT_INPUT',
            'vector2f': 'VECTOR2F_INPUT',
            'vibration': 'VIBRATION_OUTPUT',
        }
        return getattr(xr.ActionType, mapping[action_type])

    def _create_actions(self) -> None:
        for definition in self.action_definitions:
            subaction_paths = [self.subaction_paths[hand] for hand in definition.hands]
            create_info = xr.ActionCreateInfo(
                action_type=self._xr_action_type(definition.action_type),
                action_name=definition.name,
                localized_action_name=definition.localized_name,
                count_subaction_paths=len(subaction_paths),
                subaction_paths=subaction_paths,
            )
            action_handle = xr.create_action(action_set=self.handle, create_info=create_info)
            self.actions[definition.name] = action_handle
            if definition.action_type == 'pose':
                for hand in definition.hands:
                    action_space_info = xr.ActionSpaceCreateInfo(
                        action=action_handle,
                        subaction_path=self.subaction_paths[hand],
                    )
                    self.pose_spaces[(definition.name, hand)] = xr.create_action_space(
                        session=self.session.handle,
                        create_info=action_space_info,
                    )
                    self.states[(definition.name, hand)] = XRActionState(definition.name, hand, definition.action_type)
            else:
                for hand in (definition.hands or (None,)):
                    self.states[(definition.name, hand)] = XRActionState(definition.name, hand, definition.action_type)

    def _suggest_default_bindings(self) -> None:
        instance = self.session.system.instance.handle
        grouped_bindings: dict[str, list[xr.ActionSuggestedBinding]] = {}
        self._binding_arrays: dict[str, ctypes.Array] = {}
        for definition in self.action_definitions:
            action_handle = self.actions[definition.name]
            targets = definition.hands or (None,)
            for binding in definition.bindings:
                binding_targets = binding.hands or targets
                for hand in binding_targets:
                    path_string = binding.binding if not binding.hand_aware else binding.binding.format(hand=hand)
                    try:
                        path = xr.string_to_path(instance, path_string)
                    except Exception as exc:
                        self.logger.warning('Skipping invalid binding path for %s: %s (%s)', definition.name, path_string, exc)
                        continue
                    grouped_bindings.setdefault(binding.profile, []).append(xr.ActionSuggestedBinding(action_handle, path))
        for profile, bindings in grouped_bindings.items():
            try:
                if not bindings:
                    continue
                binding_array = (xr.ActionSuggestedBinding * len(bindings))(*bindings)
                self._binding_arrays[profile] = binding_array
                xr.suggest_interaction_profile_bindings(
                    instance=instance,
                    suggested_bindings=xr.InteractionProfileSuggestedBinding(
                        interaction_profile=xr.string_to_path(instance, profile),
                        count_suggested_bindings=len(bindings),
                        suggested_bindings=binding_array,
                    ),
                )
                self.logger.info('Suggested %d bindings for %s', len(bindings), profile)
            except Exception as exc:
                self.logger.warning('Could not suggest bindings for %s: %s', profile, exc)

    def link_pose(self, path: str, nodepath: NodePath) -> None:
        if path in _HAND_PATHS.values():
            hand = 'left' if path.endswith('left') else 'right'
            self.link_action_pose('grip_pose', hand, nodepath)

    def link_action_pose(self, action_name: str, hand: str, nodepath: NodePath) -> None:
        self.pose_links[(action_name, hand)] = nodepath

    def attach(self) -> None:
        xr.attach_session_action_sets(
            session=self.session.handle,
            attach_info=xr.SessionActionSetsAttachInfo(
                count_action_sets=1,
                action_sets=ctypes.pointer(self.handle),
            ),
        )

    def _action_state_get_info(self, action_name: str, hand: str | None):
        subaction_path = xr.NULL_PATH if hand is None else self.subaction_paths[hand]
        return xr.ActionStateGetInfo(action=self.actions[action_name], subaction_path=subaction_path)

    def _update_pose_state(self, action_name: str, hand: str) -> None:
        state = xr.get_action_state_pose(session=self.session.handle, get_info=self._action_state_get_info(action_name, hand))
        model = self.states[(action_name, hand)]
        model.is_active = bool(state.is_active)
        model.changed_since_last_sync = bool(getattr(state, 'changed_since_last_sync', False))
        model.tracked = False
        model.pose_valid = False
        nodepath = self.pose_links.get((action_name, hand))
        if not state.is_active:
            if nodepath is not None:
                nodepath.stash()
            return
        space_location = xr.locate_space(
            space=self.pose_spaces[(action_name, hand)],
            base_space=self.app_space.handle,
            time=self.session.frame_state.predicted_display_time,
        )
        flags = space_location.location_flags
        pose_valid = (
            flags & xr.SPACE_LOCATION_POSITION_VALID_BIT != 0 and
            flags & xr.SPACE_LOCATION_ORIENTATION_VALID_BIT != 0
        )
        model.pose_valid = bool(pose_valid)
        if pose_valid:
            model.tracked = True
            panda_pos, panda_quat = xr_pose_to_panda(space_location.pose.position, space_location.pose.orientation)
            model.current_state = {
                'position': (panda_pos.x, panda_pos.y, panda_pos.z),
                'orientation': (panda_quat.get_r(), panda_quat.get_i(), panda_quat.get_j(), panda_quat.get_k()),
            }
            if nodepath is not None:
                nodepath.unstash()
                nodepath.set_pos(panda_pos)
                nodepath.set_quat(panda_quat)
        elif nodepath is not None:
            nodepath.stash()

    def _update_scalar_state(self, definition: XRActionDefinition, hand: str | None) -> None:
        model = self.states[(definition.name, hand)]
        get_info = self._action_state_get_info(definition.name, hand)
        if definition.action_type == 'boolean':
            state = xr.get_action_state_boolean(session=self.session.handle, get_info=get_info)
            model.current_state = bool(state.current_state)
        elif definition.action_type == 'float':
            state = xr.get_action_state_float(session=self.session.handle, get_info=get_info)
            model.current_state = float(state.current_state)
        elif definition.action_type == 'vector2f':
            state = xr.get_action_state_vector2f(session=self.session.handle, get_info=get_info)
            current = getattr(state, 'current_state', None)
            model.current_state = (float(current.x), float(current.y)) if current is not None else (0.0, 0.0)
        else:
            return
        model.is_active = bool(state.is_active)
        model.changed_since_last_sync = bool(getattr(state, 'changed_since_last_sync', False))
        model.tracked = model.is_active

    def poll_actions(self) -> None:
        if not self.session.session_active():
            return
        active_action_set = xr.ActiveActionSet(self.handle, xr.NULL_PATH)
        xr.sync_actions(
            self.session.handle,
            xr.ActionsSyncInfo(count_active_action_sets=1, active_action_sets=ctypes.pointer(active_action_set)),
        )
        for definition in self.action_definitions:
            if definition.action_type == 'vibration':
                continue
            for hand in (definition.hands or (None,)):
                if definition.action_type == 'pose':
                    self._update_pose_state(definition.name, hand)
                else:
                    self._update_scalar_state(definition, hand)

    def get_state(self, action_name: str, hand: str | None = None) -> XRActionState | None:
        if hand is None:
            hand = 'right' if (action_name, 'right') in self.states else 'left' if (action_name, 'left') in self.states else None
        return self.states.get((action_name, hand))

    def get_bool(self, action_name: str, hand: str) -> bool:
        state = self.get_state(action_name, hand)
        return bool(state.current_state) if state else False

    def get_float(self, action_name: str, hand: str) -> float:
        state = self.get_state(action_name, hand)
        return float(state.current_state or 0.0) if state else 0.0

    def get_vector2f(self, action_name: str, hand: str) -> tuple[float, float]:
        state = self.get_state(action_name, hand)
        value = state.current_state if state else None
        if isinstance(value, tuple) and len(value) == 2:
            return float(value[0]), float(value[1])
        return 0.0, 0.0

    def apply_haptic(self, hand: str, amplitude: float = 0.4, duration_sec: float = 0.05, frequency: float = 0.0) -> None:
        action = self.actions.get('haptic')
        if action is None:
            return
        duration_ns = int(max(0.0, duration_sec) * 1_000_000_000)
        haptic_info = xr.HapticActionInfo(action=action, subaction_path=self.subaction_paths[hand])
        vibration = xr.HapticVibration(amplitude=amplitude, duration=duration_ns, frequency=frequency)
        xr.apply_haptic_feedback(self.session.handle, haptic_info, ctypes.byref(vibration))

    def diagnostics(self) -> list[XRActionSnapshot]:
        return [self.states[key].to_snapshot() for key in sorted(self.states)]

    def destroy(self) -> None:
        for space in self.pose_spaces.values():
            try:
                xr.destroy_space(space)
            except Exception:
                pass
        self.pose_spaces.clear()
        if self.handle is not None:
            xr.destroy_action_set(self.handle)
            self.handle = None
