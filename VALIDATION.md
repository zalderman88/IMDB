# Validation status

The shipped runtime's functional checks passed in the original workspace. The exported portable package is additionally rebuilt and checked from an extraction directory before delivery; results are recorded in `validation_result.json` when that export verification completes.

The checks execute the actual embedded JavaScript through a Node VM and lightweight DOM. They cover the independent score routes, count boundaries, missing counts, slider positions, services, year bounds, broad genre grouping/exclusions, classifications, original-language filters, country defaults, reset, sorting, pagination, review links and preferences.

No complete Android browser or pixel-layout verification is claimed. The local browser executable could not be launched in the original environment. No live source refresh is triggered by this validation.
