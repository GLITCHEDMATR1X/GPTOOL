from __future__ import annotations

from panda3d.core import CS_default, CS_yup_right, LMatrix4, LPoint3, LQuaternion

_COORD_MAT = LMatrix4.convert_mat(CS_yup_right, CS_default)


def xr_pose_to_panda(position, orientation) -> tuple[LPoint3, LQuaternion]:
    point = _COORD_MAT.xform_point(LPoint3(*position))
    quat = LQuaternion(orientation.w, orientation.x, -orientation.z, orientation.y)
    return point, quat
