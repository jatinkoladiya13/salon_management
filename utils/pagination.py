from rest_framework.pagination import PageNumberPagination

class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50

    def paginate_queryset(self, queryset, request, view=None):
        if request.GET.get("get_all", False):
            return None
        return super(CustomPageNumberPagination, self).paginate_queryset(queryset, request, view)