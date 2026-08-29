# Run evidence

`manifest.json` inventories the recovered 2026-07-27 archive without committing
its checkpoints or logs to Git. Every archived file has a SHA-256 digest. The
small rollout clips in `previews/` are byte-for-byte copies of selected archive
members and are safe to use in the recorded browser experience.

This is a historical baseline, not a substitute for the fresh current-stack run
required by issue #70. Generate the next manifest with:

```bash
make evidence SOURCE=/path/to/run-or-archive METADATA=/path/to/run-metadata.json
```

Publishing the complete archive to Hugging Face is a separate authorized step.
