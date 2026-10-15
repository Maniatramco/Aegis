-- Run as AGS_OWNER. Read-only; no credentials or password hashes selected.
SELECT u.username, d.dataset_name, g.enabled,
       g.created_at, creator.username AS created_by,
       g.updated_at, updater.username AS updated_by,
       g.created_via, g.updated_via
FROM user_dataset_tbl g
JOIN user_tbl u ON u.id = g.user_id
JOIN dataset_tbl d ON d.dataset_id = g.dataset_id
LEFT JOIN user_tbl creator ON creator.id = g.created_by
LEFT JOIN user_tbl updater ON updater.id = g.updated_by
ORDER BY u.username, d.dataset_name;

-- Every administrator has implicit access to every dataset.
SELECT u.username AS administrator, d.dataset_id, d.dataset_name
FROM user_tbl u CROSS JOIN dataset_tbl d
WHERE u.role = 'administrator'
ORDER BY d.dataset_name;
