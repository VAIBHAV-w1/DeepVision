"""
Django ORM model for Evidence table mapping to existing SQLite database.
Meta: managed = False, db_table = 'evidence'
"""
from django.db import models


class Evidence(models.Model):
    """
    Evidence model representing captured media evidence (snapshot or video clip)
    associated with a surveillance Alert.
    Maps directly to existing SQLite 'evidence' table.
    """
    id = models.AutoField(primary_key=True)
    alert = models.ForeignKey(
        'alerts.Alert',
        models.DO_NOTHING,
        db_column='alert_id',
        related_name='evidence_items',
    )
    user = models.ForeignKey(
        'accounts.User',
        models.DO_NOTHING,
        db_column='user_id',
        related_name='evidence_items',
    )
    camera = models.ForeignKey(
        'cameras.Camera',
        models.DO_NOTHING,
        db_column='camera_id',
        related_name='evidence_items',
    )
    evidence_type = models.CharField(max_length=20)  # 'snapshot', 'video'
    file_path = models.CharField(max_length=255)
    file_name = models.CharField(max_length=100)
    mime_type = models.CharField(max_length=50)
    file_size = models.IntegerField()
    captured_at = models.DateTimeField()
    duration_seconds = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'evidence'
        verbose_name = 'Evidence'
        verbose_name_plural = 'Evidence'

    def __str__(self):
        return f"Evidence {self.id} ({self.evidence_type}) - Alert {self.alert_id}"
