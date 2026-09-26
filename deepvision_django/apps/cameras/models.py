from django.db import models

class CameraGroup(models.Model):
    """Django ORM mapping for 'camera_groups' table."""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='camera_groups')
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'camera_groups'

    def __str__(self):
        return self.name


class SurveillancePreset(models.Model):
    """Django ORM mapping for 'surveillance_presets' table."""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='surveillance_presets')
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, null=True)
    enabled = models.BooleanField(default=True)
    loitering_enabled = models.BooleanField(default=True)
    restricted_entry_enabled = models.BooleanField(default=True)
    unusual_movement_enabled = models.BooleanField(default=True)
    abandoned_object_enabled = models.BooleanField(default=True)
    stationary_distance_threshold = models.FloatField(blank=True, null=True)
    stationary_time_threshold = models.FloatField(blank=True, null=True)
    loitering_radius = models.FloatField(blank=True, null=True)
    loitering_time_threshold = models.FloatField(blank=True, null=True)
    speed_fast_threshold = models.FloatField(blank=True, null=True)
    speed_slow_threshold = models.FloatField(blank=True, null=True)
    unusual_movement_persistence_seconds = models.FloatField(blank=True, null=True)
    anomaly_event_cooldown_seconds = models.FloatField(blank=True, null=True)
    anomaly_display_seconds = models.FloatField(blank=True, null=True)
    abandoned_object_time_threshold = models.FloatField(blank=True, null=True)
    abandoned_object_distance_threshold = models.FloatField(blank=True, null=True)
    person_object_association_distance = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'surveillance_presets'

    def __str__(self):
        return self.name


class Camera(models.Model):
    """Django ORM mapping for 'cameras' table."""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='cameras')
    name = models.CharField(max_length=100)
    source_type = models.CharField(max_length=20)
    source = models.CharField(max_length=255)
    location = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, default='offline')
    is_active = models.BooleanField(default=True)
    group = models.ForeignKey(CameraGroup, on_delete=models.DO_NOTHING, db_column='group_id', blank=True, null=True, related_name='cameras')
    preset = models.ForeignKey(SurveillancePreset, on_delete=models.DO_NOTHING, db_column='preset_id', blank=True, null=True, related_name='cameras')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'cameras'

    def __str__(self):
        return f"{self.name} ({self.source_type}:{self.source})"
