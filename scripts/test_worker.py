#!/usr/bin/env python3
"""Manually test the worker by creating a job and watching it process."""

import time
import logging
import uuid
import os

# Set environment variable to disable SQLAlchemy echo BEFORE any imports
os.environ['SQLALCHEMY_ECHO'] = 'False'

# Silence SQLAlchemy logging - must be done BEFORE importing anything that uses it
logging.basicConfig(level=logging.WARNING)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.orm').setLevel(logging.WARNING)

from mise.db.unit_of_work import UnitOfWork
from mise.db.models import SourceType, IngestionStatus

# Create a test job with unique source_key
unique_id = str(uuid.uuid4())[:8]
source_key = f"text:test_{unique_id}"

print("Creating test ingestion job...")
with UnitOfWork() as uow:
    job = uow.ingestions.create_request(
        source_type=SourceType.custom,
        source_key=source_key,
        source_url=None,
        request_params={
            "text": """
            Chocolate Chip Cookies

            Ingredients:
            - 2 cups all-purpose flour
            - 1 cup butter, softened
            - 1 cup brown sugar
            - 2 eggs
            - 2 cups chocolate chips

            Instructions:
            1. Preheat oven to 350°F
            2. Mix butter and sugar until fluffy
            3. Beat in eggs
            4. Stir in flour gradually
            5. Fold in chocolate chips
            6. Drop spoonfuls onto baking sheet
            7. Bake for 10-12 minutes

            Makes 24 cookies
            """
        }
    )
    uow.session.commit()
    job_id = job.id

print(f"✓ Created job ID: {job_id}")
print(f"\nNow start the worker in another terminal:")
print(f"  uv run python -m mise.worker.processor\n")
print("Monitoring job status (Ctrl+C to stop)...\n")

# Monitor the job
try:
    last_status = None
    while True:
        with UnitOfWork() as uow:
            job = uow.ingestions.get_by_id(job_id)

            if job.status != last_status:
                last_status = job.status
                print(f"[{time.strftime('%H:%M:%S')}] Status: {job.status.value}", end="")

                if job.status == IngestionStatus.processing:
                    print(f" (worker: {job.worker_id})")
                elif job.status == IngestionStatus.completed:
                    print(f" → Recipe ID: {job.recipe_id}")

                    # Show recipe details
                    recipe = uow.recipes.get_recipe_by_id(job.recipe_id)
                    print(f"\n✓ SUCCESS! Recipe created:")
                    print(f"  Title: {recipe.recipe.title}")
                    print(f"  Ingredients: {len(recipe.recipe.ingredients)}")
                    print(f"  Steps: {len(recipe.recipe.steps)}")
                    if recipe.recipe.servings:
                        print(f"  Servings: {recipe.recipe.servings}")
                    break
                elif job.status == IngestionStatus.failed:
                    print()
                    errors = job.processing_metadata.get('errors', []) if job.processing_metadata else []
                    if errors:
                        last_error = errors[-1]
                        print(f"\n✗ FAILED: {last_error.get('message', 'Unknown error')}")
                    break
                elif job.status == IngestionStatus.pending:
                    if job.retry_count > 0:
                        print(f" (retry {job.retry_count}/{job.max_retries})")
                    else:
                        print()
                else:
                    print()

        time.sleep(1)

except KeyboardInterrupt:
    print("\n\nStopped monitoring.")
    with UnitOfWork() as uow:
        job = uow.ingestions.get_by_id(job_id)
        print(f"Final status: {job.status.value}")
