---
id: REQ-ML-1
title: Filter the mission list by status
priority: 1
depends_on: []
status: pending
---
## Requirement

The mission list shows every mission the API returns. Operators want to narrow the list to open or done missions while keeping the full count in view. This REQ adds a status filter to the mission list with three choices (All, Open, Done) and a count line. It does not add sorting, search, persistence of the chosen filter, or any change to the Mission Log API.

## Acceptance criteria

1. The mission list renders one filter control with exactly three options labelled "All", "Open", and "Done". "All" is selected on first render.
2. With "All" selected, every mission the API returned is listed, in API order.
3. With "Open" selected, only missions whose status is `open` are listed. With "Done" selected, only missions whose status is `done` are listed.
4. A count line reads "Showing N of M missions", where N is the number of listed missions and M is the number the API returned. Example: 3 missions returned, 2 open, "Open" selected: the line reads "Showing 2 of 3 missions".
5. When the selected filter matches no mission, the list area shows the text "No missions match this filter." and the count line reads "Showing 0 of M missions".
6. When the API returns an empty array, the existing empty-state text "No missions on the board." is shown and no filter control is rendered.
7. Changing the filter sends no new request to the API. The missions are fetched once.
8. The full test suite (`ng test`) passes with zero failures, including the pre-existing tests.
9. Unit tests exist that cover criteria 1 through 7.
10. No file under `src/api/` changes and `api/openapi.json` does not change.
