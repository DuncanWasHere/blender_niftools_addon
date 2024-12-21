from io_scene_niftools.modules.nif_export.block_registry import block_store


class Particle:

    def __init__(self):
        self.target_game = None

    def export_particles(self, b_particle_objects, target_game):
        self.target_game = target_game

    def export_ni_particle_system(self, b_p_obj, n_parent_node):
        n_ni_particle_system = block_store.create_block("NiParticleSystem")
        n_parent_node
        return

    def export_ni_p_sys_data(self, b_p_obj, n_ni_particle_system):
        return

    def export_ni_p_sys_emitter(self, b_p_obj, n_ni_particle_system):
        return


