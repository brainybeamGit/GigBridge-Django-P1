from django.contrib import admin
from .models import (
    UserProfile, Category, Project, Proposal,
    Contract, Milestone, Payment, Conversation,
    Message, Review, ContactMessage
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'company_name', 'location', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email', 'company_name')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'project_count')
    prepopulated_fields = {'slug': ('name',)}

    def project_count(self, obj):
        return obj.projects.count()
    project_count.short_description = 'Projects'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'category', 'status', 'budget_min', 'budget_max', 'created_at')
    list_filter = ('status', 'category', 'budget_type')
    search_fields = ('title', 'client__username', 'description')
    readonly_fields = ('views_count', 'created_at', 'updated_at')


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ('project', 'freelancer', 'bid_amount', 'delivery_days', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('project__title', 'freelancer__username')


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('project', 'client', 'freelancer', 'total_amount', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ('title', 'contract', 'amount', 'status', 'due_date')
    list_filter = ('status',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client', 'freelancer', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'currency')
    readonly_fields = ('invoice_number', 'created_at')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('reviewer', 'reviewee', 'project', 'rating', 'created_at')
    list_filter = ('rating',)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'is_resolved', 'created_at')
    list_filter = ('is_resolved',)
    search_fields = ('name', 'email', 'subject')


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'created_at', 'updated_at')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'conversation', 'is_read', 'created_at')
    list_filter = ('is_read',)
