import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_professor_rank_score"),
        ("community", "0002_post_professor"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="course",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="posts",
                to="catalog.course",
            ),
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(
                fields=["course", "-created_at"], name="community_post_course_idx"
            ),
        ),
    ]
