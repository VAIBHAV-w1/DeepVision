"""
Django ORM models for Core tables mapping to existing SQLite database:
- AuditLog ('audit_logs')
- Device ('devices')
- Product ('products')
- RestrictedZone ('restricted_zones')
- DetectionProfile ('detection_profiles')

All models have Meta: managed = False, db_table = '<name>'
"""
import json
from django.db import models


class AuditLog(models.Model):
    """
    Security Audit Log for DeepVision recording user actions.
    Maps directly to existing SQLite 'audit_logs' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        blank=True,
        null=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    ip_address = models.CharField(max_length=45, blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f"AuditLog {self.id}: {self.action} on {self.resource_type} (User {self.user_id})"


class Device(models.Model):
    """
    Hardware device / client registry for edge hosts, laptops, webcams.
    Maps directly to existing SQLite 'devices' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        related_name='devices',
    )
    name = models.CharField(max_length=100)
    device_type = models.CharField(max_length=20)  # laptop, phone, webcam, edge_device, other
    identifier = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, default='offline')  # online, offline, error
    last_seen = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'devices'
        verbose_name = 'Device'
        verbose_name_plural = 'Devices'

    def __str__(self):
        return f"Device {self.name} ({self.device_type}) - Status: {self.status}"


class Product(models.Model):
    """
    Product inventory catalog item for retail / theft recognition.
    Maps directly to existing SQLite 'products' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        related_name='products',
    )
    product_id = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    sku = models.CharField(max_length=50)
    barcode = models.CharField(max_length=50, blank=True, null=True)
    field_reference_images = models.TextField(db_column='_reference_images', default='[]')
    active_status = models.BooleanField(default=True)
    recognition_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'products'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    @property
    def reference_images(self):
        try:
            return json.loads(self.field_reference_images)
        except Exception:
            return []

    def __str__(self):
        return f"Product {self.product_id}: {self.name} (SKU: {self.sku})"


class RestrictedZone(models.Model):
    """
    Restricted zone bounding box for camera feed anomaly detection.
    Maps directly to existing SQLite 'restricted_zones' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        related_name='restricted_zones',
    )
    camera = models.ForeignKey(
        'cameras.Camera',
        models.DO_NOTHING,
        db_column='camera_id',
        related_name='restricted_zones',
    )
    name = models.CharField(max_length=100)
    x1 = models.IntegerField()
    y1 = models.IntegerField()
    x2 = models.IntegerField()
    y2 = models.IntegerField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'restricted_zones'
        verbose_name = 'Restricted Zone'
        verbose_name_plural = 'Restricted Zones'

    def __str__(self):
        return f"RestrictedZone '{self.name}' on Camera {self.camera_id} (Enabled: {self.enabled})"


class DetectionProfile(models.Model):
    """
    Per-camera detection and anomaly threshold configuration.
    Maps directly to existing SQLite 'detection_profiles' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        related_name='detection_profiles',
    )
    camera = models.OneToOneField(
        'cameras.Camera',
        models.DO_NOTHING,
        db_column='camera_id',
        related_name='detection_profile',
    )
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
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'detection_profiles'
        verbose_name = 'Detection Profile'
        verbose_name_plural = 'Detection Profiles'

    def __str__(self):
        return f"DetectionProfile for Camera {self.camera_id} (User {self.user_id})"
