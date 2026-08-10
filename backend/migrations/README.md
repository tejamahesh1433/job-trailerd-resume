Numbered, one-way SQL migrations for `resumes.db`, applied automatically by
`database.init_db()` on startup and tracked in the `schema_version` table.

To add a schema change: create a new file named `NNNN_description.sql` (next
number after the highest existing one), containing the SQL to run. It will be
applied exactly once, in order, the next time the app starts. Don't edit or
renumber existing files — they represent history for databases that already
applied them.
