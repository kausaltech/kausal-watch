from django.db import models


class AzureADTenant(models.Model):
    name = models.CharField(max_length=100)
    tenant_id = models.CharField(max_length=200)
    hostname = models.CharField(max_length=100)

    def __str__(self):
        return self.name
