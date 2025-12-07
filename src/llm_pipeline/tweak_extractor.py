"""
Step 1: Tweak Extraction & Parsing

This module extracts structured modifications from review text using LLM processing.
It converts natural language descriptions of recipe changes into structured
ModificationObject instances.
"""

import json
import os
from typing import Optional

from loguru import logger
from openai import OpenAI
from pydantic import ValidationError

from .models import ModificationObject, Recipe, Review
from .prompts import build_few_shot_prompt


class TweakExtractor:
    """Extracts structured modifications from review text using LLM processing."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        Initialize the TweakExtractor.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: OpenAI model to use for extraction
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        logger.info(f"Initialized TweakExtractor with model: {model}")

    def extract_modifications(
        self,
        review: Review,
        recipe: Recipe,
        max_retries: int = 2,
    ) -> list[ModificationObject]:
        """
        Extract ALL structured modifications from a review.

        Args:
            review: Review object containing modification text
            recipe: Original recipe being modified
            max_retries: Number of retry attempts if parsing fails

        Returns:
            List of ModificationObject if extraction successful, empty list otherwise
        """
        if not review.has_modification:
            logger.warning("Review has no modification flag set")
            return []

        # Build the prompt
        prompt = build_few_shot_prompt(
            review.text, recipe.title, recipe.ingredients, recipe.instructions
        )
        

        logger.debug(
            "Extracting modifications from review: {}...".format(review.text[:100])
        )

        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=2000,  # Increased for multiple modifications
                )

                raw_output = response.choices[0].message.content
                logger.debug(f"LLM raw output: {raw_output}")

                if not raw_output:
                    logger.warning(f"Attempt {attempt + 1}: Empty response from LLM")
                    continue

                # Parse the JSON response
                raw_data = json.loads(raw_output)
                modifications_data = []
                
                modifications_data = raw_data["modifications"]
                
                
                
                # DEBUG: Check if array or single object
                if not isinstance(modifications_data, list):
                    modifications_data = [modifications_data]

                # Validate and convert to ModificationObject list
                modifications = [
                    ModificationObject(**mod) for mod in modifications_data
                ]

                logger.info(
                    f"Successfully extracted {len(modifications)} modifications "
                    f"with {sum(len(m.edits) for m in modifications)} total edits"
                )
                
                # Print each modification
                for i, mod in enumerate(modifications, 1):
                    logger.info(f"  Modification {i}: {mod.modification_type} - {mod.reasoning}")
                
                return modifications

            except json.JSONDecodeError as e:
                logger.warning(f"Attempt {attempt + 1}: Failed to parse JSON: {e}")
                if attempt == max_retries:
                    logger.error(f"Max retries reached. Raw output: {raw_output}")

            except ValidationError as e:
                logger.warning(f"Attempt {attempt + 1}: Validation error: {e}")
                if attempt == max_retries:
                    logger.error(
                        f"Max retries reached. Invalid data: {modifications_data}"
                    )

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Unexpected error: {e}")
                if attempt == max_retries:
                    return []

        return []

    # def extract_modification(
    #     self,
    #     review: Review,
    #     recipe: Recipe,
    #     max_retries: int = 2,
    # ) -> Optional[ModificationObject]:
    #     """
    #     Extract a single structured modification from a review (backwards compatibility).
        
    #     This method is kept for backwards compatibility. Use extract_modifications() 
    #     to get all modifications from a review.

    #     Args:
    #         review: Review object containing modification text
    #         recipe: Original recipe being modified
    #         max_retries: Number of retry attempts if parsing fails

    #     Returns:
    #         First ModificationObject if extraction successful, None otherwise
    #     """
    #     modifications = self.extract_modifications(review, recipe, max_retries)
        
    #     if modifications:
    #         logger.info(f"Returning first of {len(modifications)} modifications for backwards compatibility")
    #         return modifications[0]
        
    #     return None

    def extract_single_modification(
        self, reviews: list[Review], recipe: Recipe
    ) -> tuple[list[ModificationObject], Review] | tuple[None, None]:
        """
        Extract modifications from a single randomly selected review.

        Args:
            reviews: List of reviews to choose from
            recipe: Original recipe being modified

        Returns:
            Tuple of (List[ModificationObject], source_Review) if successful, (None, None) otherwise
        """
        import random

        # Filter to reviews with modifications
        modification_reviews = [r for r in reviews]

        

        
        selected_review = max(
            modification_reviews,
            key=lambda r: (r.rating or 0, len(r.text))
        )
        # Set seed for reproducibility
        # random.seed(0)
        # selected_review = random.choice(modification_reviews)
        logger.info(f"Selected review: {selected_review.text[:100]}...")

        modifications = self.extract_modifications(selected_review, recipe)
        
        if modifications:
            logger.info(f"Successfully extracted {len(modifications)} modifications from selected review")
            return modifications, selected_review
        else:
            logger.warning("Failed to extract modifications from selected review")
            return None, None

    def test_extraction(
        self, review_text: str, recipe_data: dict
    ) -> list[ModificationObject]:
        """
        Test extraction with raw text and recipe data.

        Args:
            review_text: Raw review text
            recipe_data: Raw recipe dictionary

        Returns:
            List of ModificationObject if successful, empty list otherwise
        """
        review = Review(text=review_text, has_modification=True)
        recipe = Recipe(
            recipe_id=recipe_data.get("recipe_id", "test"),
            title=recipe_data.get("title", "Test Recipe"),
            ingredients=recipe_data.get("ingredients", []),
            instructions=recipe_data.get("instructions", []),
        )

        return self.extract_modifications(review, recipe)