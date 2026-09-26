"""
Django ORM models for Notifications and NotificationPreferences tables
mapping to existing SQLite database.
Meta: managed = False, db_table = 'notifications' / 'notification_preferences'
"""
from django.db import models


class NotificationPreference(models.Model):
    """
    Per-user notification settings and anomaly filter thresholds.
    Maps directly to existing SQLite 'notification_preferences' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        related_name='notification_preference',
    )
    enabled = models.BooleanField(default=True)
    notify_critical = models.BooleanField(default=True)
    notify_high = models.BooleanField(default=True)
    notify_medium = models.BooleanField(default=True)
    notify_low = models.BooleanField(default=True)
    notify_loitering = models.BooleanField(default=True)
    notify_restricted_entry = models.BooleanField(default=True)
    notify_unusual_movement = models.BooleanField(default=True)
    notify_abandoned_object = models.BooleanField(default=True)
    notify_recording_events = models.BooleanField(default=True)
    notify_system_events = models.BooleanField(default=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'notification_preferences'
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'

    def __str__(self):
        return f"NotificationPreference User {self.user_id} (enabled={self.enabled})"


class Notification(models.Model):
    """
    Notification model mapping newly created security alerts to users.
    Maps directly to existing SQLite 'notifications' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        related_name='notifications',
    )
    alert = models.ForeignKey(
        'alerts.Alert',
        models.DO_NOTHING,
        db_column='alert_id',
        related_name='notifications',
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f"Notification {self.id} for Alert {self.alert_id} (User {self.user_id}, read={self.is_read})"
