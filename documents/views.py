from django.http import Http404, FileResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import DocumentUploadForm
from .models import Document
from django.shortcuts import get_object_or_404
from .decorators import rate_limit_uploads
import os
import mimetypes


@login_required
def serve_document(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    if request.user == document.user or request.user.is_staff:
        file_path = document.file.path

        if not os.path.exists(file_path):
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
            raise Http404("Файл документа не найден.")
        except Exception as e:
            print(f"Ошибка при отдаче файла: {e}")
            raise Http404("Произошла ошибка при попытке открыть документ.")
    else:
        raise Http404("У вас нет доступа к этому документу.")

@login_required
@rate_limit_uploads(rate_limit_seconds=1, max_uploads=1)
def documents_dashboard(request):
    user_documents = Document.objects.filter(user=request.user).order_by('-uploaded_at')

    specific_doc_types = {
        'PASSPORT': 'Паспорт',
        'INN': 'ИНН',
        'SNILS': 'СНИЛС',
    }

    forms_by_type = {}
    specific_documents_data = {}

    for doc_type_key, doc_type_display_name in specific_doc_types.items():
        existing_doc = user_documents.filter(document_type=doc_type_key).first()
        specific_documents_data[doc_type_key] = {
            'display_name': doc_type_display_name,
            'document': existing_doc,
            'form': None
        }

    if request.method == 'POST':
        form_submitted_type = request.POST.get('document_type')

        if form_submitted_type in specific_doc_types:
            form = DocumentUploadForm(
                request.POST,
                request.FILES,
                specific_document_type=form_submitted_type,
                specific_caption=specific_doc_types[form_submitted_type]
            )
            if form.is_valid():
                if Document.objects.filter(user=request.user, document_type=form_submitted_type).exists():
                    messages.error(request,
                                   f'{specific_doc_types[form_submitted_type]} уже загружен. Удалите старый, чтобы загрузить новый.')
                else:
                    document = form.save(commit=False)
                    document.user = request.user
                    document.save()
                    messages.success(request, f'{specific_doc_types[form_submitted_type]} успешно загружен!')
                return redirect('documents_dashboard')
            else:
                messages.error(request,
                               f'Ошибка при загрузке {specific_doc_types[form_submitted_type]}. Пожалуйста, проверьте форму.')
                specific_documents_data[form_submitted_type]['form'] = form
        elif request.POST.get(
                'form_type') == 'general_document_form':
            form = DocumentUploadForm(request.POST, request.FILES)
            if form.is_valid():
                document = form.save(commit=False)
                document.user = request.user
                document.document_type = 'GENERAL'
                document.save()
                messages.success(request, 'Общий документ успешно загружен!')
                return redirect('documents_dashboard')
            else:
                messages.error(request, 'Ошибка при загрузке общего документа. Пожалуйста, проверьте форму.')
                forms_by_type['general_document_form'] = form
        else:
            messages.error(request, 'Неизвестный тип формы.')

    for doc_type_key, doc_data in specific_documents_data.items():
        if not doc_data['form']:
            if not doc_data['document']:
                specific_documents_data[doc_type_key]['form'] = DocumentUploadForm(
                    specific_document_type=doc_type_key,
                    specific_caption=doc_data['display_name']
                )

    if 'general_document_form' not in forms_by_type:
        forms_by_type['general_document_form'] = DocumentUploadForm()

    context = {
        'specific_documents_data': specific_documents_data,
        'general_document_form': forms_by_type['general_document_form'],
        'user_documents': user_documents,
    }
    return render(request, 'documents/documents_dashboard.html', context)


@login_required
def delete_document(request, document_id):
    document = get_object_or_404(Document, pk=document_id, user=request.user)

    document.delete()
    messages.success(request, 'Документ успешно удален.')
    return redirect('documents_dashboard')

