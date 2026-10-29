from django.urls import path
from . import views

urlpatterns = [
    # Auth & Overview
    path('adminpanel/', views.dashboard_view, name='adminpanel_dashboard'),
    path('adminpanel/api/analytics/', views.analytics_api_view, name='adminpanel_analytics_api'),
    path('adminpanel/profile/upload-photo/', views.admin_upload_photo_view, name='adminpanel_upload_photo'),
    path('adminpanel/login/', views.admin_login_view, name='adminpanel_login'),
    path('adminpanel/logout/', views.admin_logout_view, name='adminpanel_logout'),

    # Clients (Dedicated Section for Admin to Provision & Manage Clients)
    path('adminpanel/clients/', views.clients_view, name='adminpanel_clients'),
    path('adminpanel/clients/create/', views.client_create_view, name='adminpanel_client_create'),
    path('adminpanel/clients/<int:user_id>/approve/', views.client_approve_view, name='adminpanel_client_approve'),
    path('adminpanel/clients/<int:user_id>/toggle-status/', views.client_toggle_status_view, name='adminpanel_client_toggle_status'),
    path('adminpanel/clients/<int:user_id>/delete/', views.client_delete_view, name='adminpanel_client_delete'),

    # Freelancers (Dedicated Section, only counts and manages Freelancers)
    path('adminpanel/freelancers/', views.freelancers_view, name='adminpanel_freelancers'),
    path('adminpanel/freelancers/<int:user_id>/toggle-status/', views.user_toggle_status_view, name='adminpanel_freelancer_toggle_status'),
    path('adminpanel/freelancers/<int:user_id>/delete/', views.user_delete_view, name='adminpanel_freelancer_delete'),

    # Alias for users
    path('adminpanel/users/', views.freelancers_view, name='adminpanel_users'),
    path('adminpanel/users/<int:user_id>/toggle-status/', views.user_toggle_status_view, name='adminpanel_user_toggle_status'),
    path('adminpanel/users/<int:user_id>/delete/', views.user_delete_view, name='adminpanel_user_delete'),

    # Projects
    path('adminpanel/projects/', views.projects_view, name='adminpanel_projects'),
    path('adminpanel/projects/<int:project_id>/status/', views.project_status_view, name='adminpanel_project_status'),
    path('adminpanel/projects/<int:project_id>/delete/', views.project_delete_view, name='adminpanel_project_delete'),

    # Proposals
    path('adminpanel/proposals/', views.proposals_view, name='adminpanel_proposals'),
    path('adminpanel/proposals/<int:proposal_id>/status/', views.proposal_status_view, name='adminpanel_proposal_status'),
    path('adminpanel/proposals/<int:proposal_id>/delete/', views.proposal_delete_view, name='adminpanel_proposal_delete'),

    # Contracts
    path('adminpanel/contracts/', views.contracts_view, name='adminpanel_contracts'),
    path('adminpanel/contracts/<int:contract_id>/status/', views.contract_status_view, name='adminpanel_contract_status'),
    path('adminpanel/contracts/<int:contract_id>/delete/', views.contract_delete_view, name='adminpanel_contract_delete'),

    # Payments
    path('adminpanel/payments/', views.payments_view, name='adminpanel_payments'),
    path('adminpanel/payments/<int:payment_id>/status/', views.payment_status_view, name='adminpanel_payment_status'),
    path('adminpanel/payments/<int:payment_id>/delete/', views.payment_delete_view, name='adminpanel_payment_delete'),

    # Categories
    path('adminpanel/categories/', views.categories_view, name='adminpanel_categories'),
    path('adminpanel/categories/create/', views.category_create_view, name='adminpanel_category_create'),
    path('adminpanel/categories/<int:cat_id>/edit/', views.category_edit_view, name='adminpanel_category_edit'),
    path('adminpanel/categories/<int:cat_id>/delete/', views.category_delete_view, name='adminpanel_category_delete'),

    # Reviews
    path('adminpanel/reviews/', views.reviews_view, name='adminpanel_reviews'),
    path('adminpanel/reviews/<int:review_id>/delete/', views.review_delete_view, name='adminpanel_review_delete'),
    path('adminpanel/reviews/<int:review_id>/toggle-hide/', views.review_toggle_hide_view, name='adminpanel_review_toggle_hide'),

    # Messages (Full Contact Inquiries & Replies Module)
    path('adminpanel/messages/', views.contact_messages_list_view, name='messages'),
    path('adminpanel/messages/', views.contact_messages_list_view, name='adminpanel_messages'),
    path('adminpanel/messages/<int:msg_id>/', views.contact_message_detail_view, name='message_detail'),
    path('adminpanel/messages/<int:msg_id>/', views.contact_message_detail_view, name='adminpanel_message_detail'),
    path('adminpanel/messages/<int:msg_id>/reply/', views.contact_message_reply_view, name='message_reply'),
    path('adminpanel/messages/<int:msg_id>/reply/', views.contact_message_reply_view, name='adminpanel_message_reply'),
    path('adminpanel/messages/<int:msg_id>/status/', views.contact_message_status_view, name='message_status'),
    path('adminpanel/messages/<int:msg_id>/status/', views.contact_message_status_view, name='adminpanel_message_status'),
    path('adminpanel/messages/<int:msg_id>/toggle/', views.contact_message_status_view, name='adminpanel_message_toggle'),
    path('adminpanel/messages/<int:msg_id>/delete/', views.contact_message_delete_view, name='message_delete'),
    path('adminpanel/messages/<int:msg_id>/delete/', views.contact_message_delete_view, name='adminpanel_message_delete'),
    path('adminpanel/messages/bulk/', views.contact_messages_bulk_view, name='messages_bulk_action'),
]
