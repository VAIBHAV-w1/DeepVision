from django.db import models

class Alert(models.Model):
    """Django ORM mapping for 'alerts' table."""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='alerts')
    camera = models.ForeignKey('cameras.Camera', on_delete=models.DO_NOTHING, db_column='camera_id', related_name='alerts')
    track_id = models.IntegerField(blank=True, null=True)
    event_type = models.CharField(max_length=50)
    title = models.CharField(max_length=100)
    message = models.TextField()
    severity = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default='new')
    confidence = models.FloatField(blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    detected_at = models.DateTimeField()
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    response_state = models.CharField(max_length=20, default='NEW', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'alerts'

    def __str__(self):
        return f"Alert #{self.id}: {self.title} ({self.severity})"


class IncidentCase(models.Model):
    """Django ORM mapping for 'incident_cases' table."""
    id = models.AutoField(primary_key=True)
    case_number = models.CharField(max_length=50)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='incident_cases')
    alert = models.ForeignKey(Alert, on_delete=models.DO_NOTHING, db_column='alert_id', blank=True, null=True, related_name='incident_cases')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(max_length=20)
    status = models.CharField(max_length=20)
    assigned_to = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'incident_cases'

    def __str__(self):
        return f"Case {self.case_number}: {self.title}"


class IncidentNote(models.Model):
    """Django ORM mapping for 'incident_notes' table."""
    id = models.AutoField(primary_key=True)
    alert = models.ForeignKey(Alert, on_delete=models.DO_NOTHING, db_column='alert_id', related_name='incident_notes')
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='incident_notes')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'incident_notes'


class IncidentPolicy(models.Model):
    """Django ORM mapping for 'incident_policies' table."""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='incident_policies')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    enabled = models.BooleanField(default=True)
    severity = models.CharField(max_length=20)
    initial_response_minutes = models.IntegerField()
    escalation_minutes = models.IntegerField()
    resolution_minutes = models.IntegerField()
    auto_escalate = models.BooleanField(default=True)
    auto_create_case = models.BooleanField(default=True)
    notify_on_escalation = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'incident_policies'


class IncidentPlaybook(models.Model):
    """Django ORM mapping for 'incident_playbooks' table."""
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.DO_NOTHING, db_column='user_id', related_name='incident_playbooks')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    enabled = models.BooleanField(default=True)
    priority = models.IntegerField()
    severity = models.CharField(max_length=20, blank=True, null=True)
    event_type = models.CharField(max_length=50, blank=True, null=True)
    camera = models.ForeignKey('cameras.Camera', on_delete=models.DO_NOTHING, db_column='camera_id', blank=True, null=True, related_name='incident_playbooks')
    group = models.ForeignKey('cameras.CameraGroup', on_delete=models.DO_NOTHING, db_column='group_id', blank=True, null=True, related_name='incident_playbooks')
    create_case = models.BooleanField(default=True)
    auto_escalate = models.BooleanField(default=True)
    send_notification = models.BooleanField(default=True)
    notification_severity = models.CharField(max_length=20, blank=True, null=True)
    apply_sla_policy = models.BooleanField(default=True)
    cooldown_seconds = models.IntegerField(default=300)
    last_executed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'incident_playbooks'
