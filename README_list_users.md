run this in the PythonAnywhere web app console to list users:

```commandline
python manage.py shell -c "from django.contrib.auth.models import User; print(list(User.objects.filter(is_superuser=True).values('username', 'email')))"  

```