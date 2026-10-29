from django.contrib import admin
from .models import (
    UserProfile, Category, Project, Proposal,
    Contract, Milestone, Payment, Conversation,
    Message, Review, ContactMessage, ContactReply, Notification
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
    list_display = ('contract', 'reviewer', 'reviewee', 'overall_rating', 'would_recommend', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'overall_rating', 'would_recommend', 'created_at')
    search_fields = ('reviewer__username', 'reviewee__username', 'project__title', 'comment')
    readonly_fields = ('overall_rating', 'created_at', 'updated_at')
    actions = ['hide_reviews', 'unhide_reviews']

    def hide_reviews(self, request, queryset):
        updated = queryset.update(is_hidden=True)
        for r in queryset:
            if hasattr(r.reviewee, 'profile'):
                r.reviewee.profile.recalculate_stats()
        self.message_user(request, f"{updated} review(s) hidden from platform.")
    hide_reviews.short_description = "Hide selected reviews from platform"

    def unhide_reviews(self, request, queryset):
        updated = queryset.update(is_hidden=False)
        for r in queryset:
            if hasattr(r.reviewee, 'profile'):
                r.reviewee.profile.recalculate_stats()
        self.message_user(request, f"{updated} review(s) unhidden.")
    unhide_reviews.short_description = "Unhide selected reviews"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')


class ContactReplyInline(admin.TabularInline):
    model = ContactReply
    extra = 0
    readonly_fields = ('replied_by', 'subject', 'body', 'sent_at', 'email_sent', 'error')
    can_delete = False
    show_change_link = True


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'name', 'email', 'subject', 'topic', 'status', 'created_at', 'read_at')
    list_filter = ('status', 'topic', 'is_resolved', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message', 'topic', 'id')
    readonly_fields = ('ticket_number', 'ip_address', 'created_at', 'updated_at', 'read_at')
    inlines = [ContactReplyInline]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'created_at', 'updated_at')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'conversation', 'is_read', 'created_at')
    list_filter = ('is_read',)
