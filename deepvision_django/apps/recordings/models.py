from django.db import models

class Recording(models.Model):
    """Django ORM mapping for 'recordings' table."""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='recordings')
    camera = models.ForeignKey('cameras.Camera', on_delete=models.DO_NOTHING, db_column='camera_id', related_name='recordings')
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=255)
    duration_seconds = models.FloatField(default=0.0)
    file_size = models.IntegerField(default=0)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='recording')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'recordings'

    def __str__(self):
        return f"Recording #{self.id}: {self.filename} ({self.status})"
