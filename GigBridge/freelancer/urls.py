from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='freelancer_dashboard'),
    path('profile/', views.profile_view, name='freelancer_profile'),
    path('profile/delete/', views.freelancer_delete_account_view, name='freelancer_delete_account'),
    path('proposals/', views.proposals_view, name='freelancer_proposals'),
    path('contracts/', views.contracts_view, name='freelancer_contracts'),
    path('earnings/', views.earnings_view, name='freelancer_earnings'),
    path('contracts/<int:pk>/', views.contract_detail_view, name='freelancer_contract_detail'),
    path('contracts/<int:contract_id>/submit-delivery/', views.submit_delivery_view, name='freelancer_submit_delivery'),
    path('messages/', views.messages_view, name='freelancer_messages'),
    path('messages/<int:pk>/', views.conversation_detail_view, name='freelancer_conversation_detail'),
    path('messages/<int:pk>/delete/', views.conversation_delete_view, name='freelancer_conversation_delete'),
]
