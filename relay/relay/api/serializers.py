class SimpleSerializer:
    @staticmethod
    def serialize(instance):
        raise NotImplementedError

    @classmethod
    def serialize_many(cls, instances):
        return [cls.serialize(instance) for instance in instances]


class ConnectedTallyLightSerializer(SimpleSerializer):
    @staticmethod
    def serialize(instance):
        return {field: instance[field]
                for field in ("deviceId", "online", "settings")}


class SettingsUpdateSerializer(SimpleSerializer):
    @staticmethod
    def serialize(instance):
        return {field: instance[field]
                for field in ("deviceId", "state", "operationId")}


class SettingsUpdatesSerializer(SimpleSerializer):
    @staticmethod
    def serialize(instance):
        return {"updates": SettingsUpdateSerializer.serialize_many(instance["updates"])}


class LiveTallyLightSerializer(SimpleSerializer):
    @staticmethod
    def serialize(instance):
        return {field: instance[field]
                for field in ("deviceId", "name", "source", "status", "settings")}


class LiveSnapshotSerializer(SimpleSerializer):
    @staticmethod
    def serialize(instance):
        return {
            "transmitter_online": instance["transmitter_online"],
            "program": instance["program"],
            "preview": instance["preview"],
            "updated_at": instance["updated_at"],
            "tally_lights": LiveTallyLightSerializer.serialize_many(instance["tally_lights"]),
        }
