"""Main module for exporting particle animation blocks."""

from io_scene_niftools.modules.nif_export.animation.common import AnimationCommon


class ParticleAnimation(AnimationCommon):

    def export_particle_animations(self, n_ni_controller_sequence, b_controlled_blocks):
        return