"""Import sequence-driven particle controller channels."""

from ....modules.nif_import.animation import Animation
from ....utils.logging import NifLog
from nifgen.formats.nif import classes as NifClasses


class ParticleAnimation(Animation):
    """Map FNV particle controller-sequence values onto ParticleSettings actions."""

    @staticmethod
    def find_settings(target_name):
        # Imported particle systems are registered by their original NIF block,
        # which avoids ambiguity if Blender had to suffix an object name.
        from ....modules.nif_import.particle import DICT_PARTICLE_SYSTEMS

        for n_system, b_obj in DICT_PARTICLE_SYSTEMS.items():
            if str(n_system.name) == target_name and b_obj.particle_systems:
                return b_obj.particle_systems[0].settings
        return None

    def import_sequence_controlled_block(self, controlled, sequence):
        """Import a supported particle controlled block into the shared sequence action."""

        n_controller = controlled.controller
        controller_type = str(controlled.controller_type or "")
        if not controller_type and n_controller is not None:
            controller_type = type(n_controller).__name__
        interpolator_id = str(controlled.interpolator_id or "")
        if "PSys" not in controller_type:
            return False

        target_name = str(controlled.target_name or "")
        if not target_name:
            target_name = str(controlled.get_node_name() or "")
        b_settings = self.find_settings(target_name)
        if b_settings is None:
            NifLog.warn(
                f"The sequence animates particle system '{target_name}', "
                "which was not imported, so the channel is skipped.")
            return True

        n_interpolator = controlled.interpolator
        if isinstance(n_interpolator, NifClasses.NiBoolInterpolator):
            value_type = "BOOL"
        elif isinstance(n_interpolator, NifClasses.NiFloatInterpolator):
            value_type = "FLOAT"
        else:
            # Reset-on-loop and a few engine-private particle controllers carry
            # no scalar interpolator. They remain preserved in the typed block
            # graph, but do not have a Blender fcurve to create.
            return True

        nif_ps = b_settings.nif_particle_system
        channel_index = len(nif_ps.controller_channels)
        channel = nif_ps.controller_channels.add()
        channel.sequence_name = str(sequence.name or "")
        channel.controller_type = controller_type
        channel.controller_id = str(controlled.controller_id or "")
        channel.interpolator_id = interpolator_id
        channel.value_type = value_type
        value_property = "bool_value" if value_type == "BOOL" else "float_value"
        data_path = (
            f"nif_particle_system.controller_channels[{channel_index}]."
            f"{value_property}")

        n_data = self.get_interpolator_data(controlled.interpolator)
        if n_data and getattr(n_data, "keys", None):
            times, values = self.get_keys_values(n_data.keys)
            interpolation = self.get_b_interp_from_n_interp(n_data.interpolation)
            tangents = (self.get_nif_tangents(n_data.keys, n_data.interpolation)
                        if value_type == "FLOAT" else None)
        else:
            value = getattr(controlled.interpolator, "value", None)
            if value is None:
                return True
            times = [sequence.start_time, sequence.stop_time]
            values = [value, value]
            interpolation = "CONSTANT"
            tangents = None

        if value_type == "BOOL":
            values = [int(bool(value)) for value in values]
            interpolation = "CONSTANT"
            channel.bool_value = bool(values[0])
        else:
            channel.float_value = float(values[0])

        b_action = self.create_action(
            b_settings, f"{target_name}-ParticleAction", str(sequence.name or ""))
        flags = n_controller.flags if n_controller is not None else 0
        self.add_keys(
            b_settings, b_action, data_path, (0,), flags,
            times, values, interpolation, tangents=tangents)
        self.max_key_time = max(self.max_key_time, max(times))
        return True
