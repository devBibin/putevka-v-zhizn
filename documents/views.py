from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import DocumentUploadForm
from .models import Document

@login_required
def documents_dashboard(request):
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.user = request.user
            document.save()
            messages.success(request, 'Документ успешно загружен!')
            return redirect('documents_dashboard')
        else:
            messages.error(request, 'Ошибка при загрузке документа. Пожалуйста, проверьте форму.')
    else:
        form = DocumentUploadForm()

    documents = Document.objects.filter(user=request.user).order_by('-uploaded_at')

    context = {
        'form': form,
        'documents': documents,
    }
    return render(request, 'documents/documents_dashboard.html', context)
