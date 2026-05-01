from __future__ import annotations

import xr


class Space:
    def __init__(self, session, reference_space_type: str = 'Stage'):
        self.reference_space_type = reference_space_type
        reference_space_create_info = self.get_xr_reference_space_create_info(reference_space_type)
        self.handle = xr.create_reference_space(session.handle, reference_space_create_info)

    @classmethod
    def supported_types(cls, session) -> set[str]:
        supported = set()
        raw_types = xr.enumerate_reference_spaces(session.handle)
        for raw in raw_types:
            ref_type = xr.ReferenceSpaceType(raw)
            supported.add(str(ref_type).split('.')[-1].title())
        return supported

    @classmethod
    def create_best(cls, session, preferred: tuple[str, ...] = ('Stage', 'Local')) -> 'Space':
        supported = cls.supported_types(session)
        for name in preferred:
            if name in supported:
                return cls(session, reference_space_type=name)
        return cls(session, reference_space_type='Local')

    def get_xr_reference_space_create_info(self, reference_space_type: str) -> xr.ReferenceSpaceCreateInfo:
        create_info = xr.ReferenceSpaceCreateInfo(pose_in_reference_space=xr.Posef())
        mapping = {
            'View': xr.ReferenceSpaceType.VIEW,
            'Local': xr.ReferenceSpaceType.LOCAL,
            'Stage': xr.ReferenceSpaceType.STAGE,
        }
        try:
            create_info.reference_space_type = mapping[reference_space_type]
        except KeyError as exc:
            raise ValueError(f"Unknown reference space type '{reference_space_type}'") from exc
        return create_info

    def destroy(self):
        if self.handle is not None:
            xr.destroy_space(self.handle)
            self.handle = None
