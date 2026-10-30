from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from client.models import Contract, Milestone, Submission, Payment


class Command(BaseCommand):
    help = "Repairs contract milestones: sets order, enforces sequential statuses, moves mislinked submissions, and validates/repairs due dates."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Starting Contract & Milestone Repair ==="))
        contracts = Contract.objects.all().order_by('id')
        changes_count = 0

        for contract in contracts:
            self.stdout.write(f"\nProcessing Contract #{contract.id}: '{contract.project.title}' (Status: {contract.status})")
            milestones = list(contract.milestones.all().order_by('id'))
            if not milestones:
                self.stdout.write(self.style.WARNING("  No milestones found for this contract."))
                continue

            # 1. Determine and set milestone orders (1, 2, 3...)
            ordered_milestones = []
            if len(milestones) == 3:
                p1 = next((m for m in milestones if m.milestone_type == 'advance' or 'phase 1' in m.title.lower()), None)
                p2 = next((m for m in milestones if m.milestone_type == 'regular' or 'phase 2' in m.title.lower()), None)
                p3 = next((m for m in milestones if m.milestone_type == 'final' or 'phase 3' in m.title.lower()), None)
                if p1 and p2 and p3:
                    ordered_milestones = [p1, p2, p3]
            
            if not ordered_milestones:
                def type_rank(m):
                    if m.milestone_type == 'advance' or 'phase 1' in m.title.lower() or 'advance' in m.title.lower():
                        return 1
                    if m.milestone_type == 'final' or 'phase 3' in m.title.lower() or 'final' in m.title.lower():
                        return 99
                    return 2
                ordered_milestones = sorted(milestones, key=lambda m: (type_rank(m), m.id))

            for idx, ms in enumerate(ordered_milestones, start=1):
                if ms.order != idx:
                    self.stdout.write(f"  [ORDER] Set Milestone #{ms.id} ('{ms.title[:30]}...') order: {ms.order} -> {idx}")
                    ms.order = idx
                    ms.save(update_fields=['order'])
                    changes_count += 1

            # 2. Check and fix Due Dates sequence (increasing order)
            for idx in range(len(ordered_milestones)):
                curr_ms = ordered_milestones[idx]
                if idx > 0:
                    prev_ms = ordered_milestones[idx - 1]
                    if curr_ms.due_date and prev_ms.due_date and curr_ms.due_date <= prev_ms.due_date:
                        new_due = prev_ms.due_date + timedelta(days=max(3, 7 * (curr_ms.order - prev_ms.order)))
                        self.stdout.write(self.style.WARNING(
                            f"  [DUE DATE FIX] Flagged out-of-order due date: Phase {curr_ms.order} due ({curr_ms.due_date}) was <= Phase {prev_ms.order} due ({prev_ms.due_date}). Adjusted Phase {curr_ms.order} due to {new_due}"
                        ))
                        curr_ms.due_date = new_due
                        curr_ms.save(update_fields=['due_date'])
                        changes_count += 1

            # 3. Check for Mislinked Submissions or Premature Payments on Later Milestones
            # If an earlier milestone is unpaid, any payment or submission on later milestones was caused by the skipping bug.
            first_unpaid_idx = next((i for i, m in enumerate(ordered_milestones) if m.status != 'paid'), len(ordered_milestones))
            
            # Check if any later milestone (after first_unpaid_idx) has payments or submissions
            for later_idx in range(first_unpaid_idx + 1, len(ordered_milestones)):
                later_ms = ordered_milestones[later_idx]
                target_ms = ordered_milestones[first_unpaid_idx]

                # If later_ms has a premature payment caused by the bug
                premature_payments = contract.payments.filter(milestone=later_ms)
                if premature_payments.exists():
                    self.stdout.write(self.style.WARNING(
                        f"  [PAYMENT FIX] Removing premature payment on Phase {later_ms.order} (#{later_ms.id}) because earlier Phase {target_ms.order} (#{target_ms.id}) was never paid."
                    ))
                    premature_payments.delete()
                    later_ms.status = 'pending'
                    later_ms.save(update_fields=['status'])
                    changes_count += 1

                # If later_ms has submission notes or file, move them to target_ms
                if later_ms.submission_notes or later_ms.deliverable_link or later_ms.submission_file:
                    self.stdout.write(self.style.NOTICE(
                        f"  [SUBMISSION REPAIR] Moving mislinked submission from Phase {later_ms.order} to active Phase {target_ms.order}..."
                    ))
                    target_ms.submission_notes = later_ms.submission_notes
                    target_ms.deliverable_link = later_ms.deliverable_link
                    target_ms.submission_file = later_ms.submission_file
                    target_ms.revision_notes = later_ms.revision_notes
                    target_ms.submitted_at = later_ms.submitted_at or timezone.now()
                    # If revision was requested, keep revision_requested, else submitted
                    target_ms.status = 'revision_requested' if later_ms.revision_notes else 'submitted'
                    target_ms.save()

                    # Clear later_ms
                    later_ms.submission_notes = ''
                    later_ms.deliverable_link = ''
                    later_ms.submission_file = None
                    later_ms.revision_notes = ''
                    later_ms.submitted_at = None
                    later_ms.status = 'pending'
                    later_ms.save()
                    changes_count += 1

            # 4. Strict Sequential Status Recomputation
            found_first_unpaid = False
            for idx, ms in enumerate(ordered_milestones):
                has_completed_payment = contract.payments.filter(milestone=ms, status='completed').exists()
                if has_completed_payment:
                    if ms.status != 'paid':
                        ms.status = 'paid'
                        ms.save(update_fields=['status'])
                        changes_count += 1
                elif not found_first_unpaid:
                    found_first_unpaid = True
                    # Active milestone
                    if ms.status == 'pending':
                        ms.status = 'in_progress'
                        ms.save(update_fields=['status'])
                        self.stdout.write(f"  [STATUS] Set active Phase {ms.order} (#{ms.id}) status to 'in_progress'")
                        changes_count += 1
                    else:
                        self.stdout.write(f"  [STATUS] Active Phase {ms.order} (#{ms.id}) is '{ms.status}'")
                else:
                    # Subsequent milestone must be locked (pending)
                    if ms.status != 'pending':
                        self.stdout.write(self.style.WARNING(
                            f"  [STATUS LOCK] Set subsequent Phase {ms.order} (#{ms.id}) from '{ms.status}' to 'pending' (locked)"
                        ))
                        ms.status = 'pending'
                        ms.save(update_fields=['status'])
                        changes_count += 1

            # 5. Contract Status Recalculation
            all_paid = not any(m.status != 'paid' for m in ordered_milestones)
            if all_paid and contract.status != 'completed':
                self.stdout.write(f"  [CONTRACT] All milestones paid -> set contract to 'completed'")
                contract.status = 'completed'
                contract.save(update_fields=['status'])
                changes_count += 1
            elif not all_paid and contract.status == 'completed':
                self.stdout.write(self.style.WARNING(f"  [CONTRACT] Unpaid milestones exist -> set contract to 'active'"))
                contract.status = 'active'
                contract.save(update_fields=['status'])
                changes_count += 1

            # 6. Ensure Submission records exist for any milestone with deliverables
            for ms in ordered_milestones:
                if (ms.submission_notes or ms.deliverable_link or ms.submission_file) and not ms.submissions.exists():
                    Submission.objects.create(
                        milestone=ms,
                        contract=contract,
                        freelancer=contract.freelancer,
                        submission_notes=ms.submission_notes,
                        deliverable_link=ms.deliverable_link,
                        submission_file=ms.submission_file,
                        created_at=ms.submitted_at or timezone.now()
                    )
                    changes_count += 1

        self.stdout.write(self.style.SUCCESS(f"\nRepair complete! Total repairs/adjustments made: {changes_count}"))
