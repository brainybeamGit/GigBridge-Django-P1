from django.urls import path
from . import views

urlpatterns = [
    # ─── Auth ───
    path('accounts/register/', views.register_view, name='register'),
    path('accounts/login/', views.login_view, name='login'),
    path('accounts/logout/', views.logout_view, name='logout'),
    path('accounts/forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('accounts/verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('accounts/reset-password/', views.reset_password_view, name='reset_password'),

    # ─── Public ───
    path('', views.home_view, name='home'),
    path('projects/', views.project_list_view, name='project_list'),
    path('projects/<int:pk>/', views.project_detail_view, name='project_detail'),
    path('categories/', views.category_list_view, name='category_list'),
    path('about/', views.about_view, name='about'),
    path('how-it-works/', views.how_it_works_view, name='how_it_works'),
    path('contact/', views.contact_view, name='contact'),
    path('reviews/', views.reviews_view, name='reviews'),

    # ─── Client Dashboard ───
    path('client/dashboard/', views.client_dashboard_view, name='client_dashboard'),
    path('client/projects/', views.client_projects_view, name='client_projects'),
    path('client/projects/create/', views.client_project_create_view, name='client_project_create'),
    path('client/projects/<int:pk>/edit/', views.client_project_edit_view, name='client_project_edit'),
    path('client/projects/<int:pk>/delete/', views.client_project_delete_view, name='client_project_delete'),
    path('client/projects/<int:pk>/close/', views.client_project_close_view, name='client_project_close'),
    path('client/projects/<int:pk>/confirm-delete/', views.client_confirm_delete_view, name='client_project_confirm_delete'),
    path('client/proposals/', views.client_proposals_view, name='client_proposals'),
    path('client/proposals/<int:proposal_id>/accept/', views.client_proposal_accept_view, name='client_proposal_accept'),
    path('client/proposals/<int:proposal_id>/reject/', views.client_proposal_reject_view, name='client_proposal_reject'),
    path('client/contracts/', views.client_contracts_view, name='client_contracts'),
    path('client/contracts/<int:pk>/', views.client_contract_detail_view, name='client_contract_detail'),
    path('client/milestones/', views.client_milestones_view, name='client_milestones'),
    path('client/milestones/<int:pk>/approve/', views.client_milestone_approve_view, name='client_milestone_approve'),
    path('client/milestones/<int:pk>/revision/', views.client_milestone_revision_view, name='client_milestone_revision'),
    path('client/payments/', views.client_payments_view, name='client_payments'),
    path('client/payments/<int:pk>/invoice/', views.client_invoice_view, name='client_invoice'),
    path('client/payments/<int:pk>/invoice/detail/', views.client_invoice_view, name='client_invoice_detail'),
    path('client/payments/checkout/<int:milestone_pk>/', views.client_payment_checkout_view, name='client_payment_checkout'),
    path('client/payments/create-order/', views.client_payment_create_order_view, name='client_payment_create_order'),
    path('client/payments/verify/', views.client_payment_verify_view, name='client_payment_verify'),
    # ─── Messaging (Part A) ───
    path('messages/', views.messages_inbox_view, name='messages_inbox'),
    path('messages/<int:conversation_id>/', views.conversation_detail_view, name='conversation_detail'),
    path('messages/<int:conversation_id>/send/', views.send_message_view, name='send_message'),
    path('messages/<int:conversation_id>/fetch/', views.fetch_new_messages_view, name='fetch_new_messages'),
    path('messages/<int:conversation_id>/delete/', views.conversation_delete_view, name='conversation_delete'),
    path('messages/start/', views.start_conversation_view, name='start_conversation'),
    path('client/messages/', views.messages_inbox_view, name='client_messages'),
    path('client/messages/<int:pk>/', views.conversation_detail_view, name='client_conversation_detail'),
    path('client/messages/<int:pk>/delete/', views.conversation_delete_view, name='client_conversation_delete'),

    # ─── Rating & Reviews (Part A & B) ───
    path('contracts/<int:contract_id>/review/', views.contract_review_create_view, name='contract_review_create'),
    path('contracts/<int:contract_id>/review/edit/', views.contract_review_edit_view, name='contract_review_edit'),
    path('freelancers/<int:id>/', views.freelancer_public_profile_view, name='freelancer_public_profile'),
    path('freelancer/profile/<int:id>/', views.freelancer_public_profile_view, name='freelancer_public_profile_alias'),
    path('client/reviews/', views.client_reviews_view, name='client_reviews'),
    path('client/reviews/create/<int:contract_pk>/', views.contract_review_create_view, name='client_review_create'),
    path('client/profile/', views.client_profile_view, name='client_profile'),
    path('client/profile/delete/', views.client_delete_account_view, name='client_delete_account'),
]
