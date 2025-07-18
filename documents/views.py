import mimetypes
import os
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, FileResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect

from .decorators import rate_limit_uploads
from .forms import DocumentUploadForm
from .models import Document

logger = logging.getLogger(__name__)

@login_required
def serve_document(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    if request.user == document.user or request.user.is_staff:
        file_path = document.file.path

        if not os.path.exists(file_path):
            logger.info('Документ не найден на сервере.')
            raise Http404("Документ не найден на сервере.")

        try:
            content_type, encoding = mimetypes.guess_type(file_path)

            if content_type is None:
                content_type = 'application/octet-stream'

            response = FileResponse(open(file_path, 'rb'),
                                    content_type=content_type)

            response['Content-Disposition'] = f'inline; filename="{document.file.name.split("/")[-1]}"'

            return response
        except FileNotFoundError:
            logger.info('Файл документа не найден на сервере.')
            raise Http404("Файл документа не найден.")
        except Exception as e:
            logger.error(f"Ошибка при отдаче файла: {e}")
            raise Http404("Произошла ошибка при попытке открыть документ.")
    else:
        logger.info(f'Пользователь {request.user.username} пытается получить доступ к документам {document.user.username}')
        raise Http404("У вас нет доступа к этому документу.")


@login_required
@rate_limit_uploads(rate_limit_seconds=1, max_uploads=1)
def documents_dashboard(request):
    user_documents = Document.objects.filter(user=request.user).filter(is_deleted=False).order_by('-uploaded_at')

    document_upload_form = DocumentUploadForm()

    if request.method == 'POST':
        if request.POST.get('form_type') == 'general_document_form':
            form = DocumentUploadForm(request.POST, request.FILES)
            if form.is_valid():
                document = form.save(commit=False)
                document.user = request.user
                document.save()
                messages.success(request, 'Общий документ успешно загружен!')
                logger.info(f'{request.user.username} загрузил файл {document.file.name}')
                return redirect('documents_dashboard')
            else:
                logger.error(f'{request.user.username} ошибка при загрузке файла')
                messages.error(request, 'Ошибка при загрузке общего документа. Пожалуйста, проверьте форму.')
                document_upload_form = form
        else:
            logger.error(f'{request.user.username} неизвестный тип формы')
            messages.error(request, 'Неизвестный тип формы.')

    context = {
        'general_document_form': document_upload_form,
        'user_documents': user_documents,
    }
    return render(request, 'documents/documents_dashboard.html', context)


@login_required
def delete_document(request, document_id):
    document = get_object_or_404(Document, pk=document_id, user=request.user)

    document.is_deleted = True
    document.save()
    messages.success(request, 'Документ успешно удален.')
    logger.info(f'Файл {document.file.name} помечен как удалённый')
    return redirect('documents_dashboard')
