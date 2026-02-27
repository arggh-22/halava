from tortoise import fields, models

class Notification(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.BigIntField(index=True)
    type = fields.CharField(max_length=50)  # 'new_response', 'contact_bought', 'system'
    title = fields.CharField(max_length=255)
    body = fields.TextField()
    payload = fields.JSONField(null=True)
    is_read = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "notifications"
