import threading


from django.test import TransactionTestCase as Transaction

from lineops.core.services.allocation_service import AllocationService


class AllocationConcurrencyTest(Transaction):

    reset_sequences = True

    def test_concurrent_allocation(self):
        results = []

        def attempt():
            try:
                AllocationService.allocate_line(
                    employee=self.employee,
                    phone_line=line=self.line,
                    allocation_by=self.admin
                )
                results.append("success")
            except Exception as e:
                results.append(f"error: {str(e)}")

                t1 = threading.Thread(target=attempt)
                t2 = threading.Thread(target=attempt)
                t1.start()
                t2.start()
                t1.join()
                t2.join()

                self.assertEqual(results.count("success"), 1)
                self.assertEqual(results.count("error"), 1)
