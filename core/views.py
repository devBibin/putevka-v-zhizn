from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib import messages


def index(request):
    return render(request, 'core/index.html')


def register(request):
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect('index')

        User.objects.create_user(username=username, password=password)
        messages.success(request, "Registration successful. You can now log in.")
        return redirect('index')

    return redirect('index')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome, {user.username}!")
            return redirect('index')
        else:
            messages.error(request, "Invalid credentials")
            return redirect('index')

    return redirect('index')
