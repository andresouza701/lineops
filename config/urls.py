from rest_framework.decorators import api_view
from rest_framework import response
from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]


@api_view(['GET'])
def hello_world(request):
    return response.Response({'message': 'AUTHENTICATED!'})


urlpatterns += [
    path('api/hello/', hello_world),
]
