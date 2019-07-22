from pprint import pprint
from django.http import Http404
from django.http import StreamingHttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import ungettext, ugettext_lazy as _

try:
    from wagtail.admin import messages
    from wagtail.core.models import Page
except ImportError:  # fallback for Wagtail <2.0
    from wagtail.wagtailadmin import messages
    from wagtail.wagtailcore.models import Page

from .exporting import export_pages
from .forms import ExportForm
from .forms import ImportFromFileForm
from .forms import PageTypeForm
from .importing import import_pages


def index(request):
    return render(request, 'wagtailcsvimport/index.html')


def import_from_file(request):
    """
    Bulk create new pages based on fields defined in a CSV file

    The source site's base url and the source page id of the point in the
    tree to import defined what to import and the destination parent page
    defines where to import it to.
    """
    if request.method == 'POST':
        form = ImportFromFileForm(request.POST, request.FILES)
        if form.is_valid():
            import_data = form.cleaned_data['file'].read().decode('utf-8')
            parent_page = form.cleaned_data['parent_page']

            try:
                page_count = import_pages(import_data, parent_page)
            except Exception as e:
                pprint(vars(e))
                messages.error(request, _(
                    "Import failed: %(reason)s") % {'reason': e}
                )
            else:
                messages.success(request, ungettext(
                    "%(count)s page imported.",
                    "%(count)s pages imported.",
                    page_count) % {'count': page_count}
                )
            return redirect('wagtailadmin_explore', parent_page.pk)
    else:
        form = ImportFromFileForm()

    return render(request, 'wagtailcsvimport/import_from_file.html', {
        'form': form,
        'request': request,
    })


def export_to_file(request):
    """Export a part of the page tree to a CSV file.

    User will see a form to choose one particular page type. If
    selected only pages of that type will be exported, and its
    specific fields could be selected. Otherwise only the base Page
    model's fields will be exported.

    HTTP response will be streamed, to reduce memory usage and avoid
    response timeouts.

    """
    export_form = None
    if request.method == 'GET':
        page_type_form = PageTypeForm(request.GET)
        if page_type_form.is_valid():
            page_model = page_type_form.get_page_model()
            export_form = ExportForm(page_model=page_model)
    elif request.method == 'POST':
        page_type_form = PageTypeForm(request.POST)
        if page_type_form.is_valid():
            content_type = page_type_form.get_content_type()
            page_model = content_type.model_class() if content_type else None
            export_form = ExportForm(request.POST, page_model=page_model)
            if export_form.is_valid():
                fields = export_form.cleaned_data['fields']
                only_published = export_form.cleaned_data['only_published']
                csv_rows = export_pages(
                    export_form.cleaned_data['root_page'],
                    content_type=content_type,
                    fieldnames=fields,
                    only_published=only_published
                )
                response = StreamingHttpResponse(csv_rows, content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="wagtail_export.csv"'
                return response

    return render(request, 'wagtailcsvimport/export_to_file.html', {
        'export_form': export_form,
        'page_type_form': page_type_form,
        'request': request,
    })


def export(request, page_id, only_published=False):
    """
    API endpoint of this source site to export a part of the page tree
    rooted at page_id

    Requests are made by a destination site's import_from_api view.
    """
    if only_published:
        pages = Page.objects.live()
    else:
        pages = Page.objects.all()

    try:
        root_page = pages.get(pk=page_id)
    except Page.DoesNotExist:
        raise Http404

    csv_rows = export_pages(root_page, content_type=root_page.content_type,
                            only_published=only_published)
    response = StreamingHttpResponse(csv_rows, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="wagtail_export.csv"'
    return response