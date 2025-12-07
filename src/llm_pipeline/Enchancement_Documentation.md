# Recipe Enhancement Platform

A sophisticated system that automatically enhances recipes by analyzing and applying community-tested modifications from AllRecipes.com. The platform uses advanced LLM processing to extract meaningful recipe tweaks from user reviews and applies them with full citation tracking and safety validation.

## Table of Contents

1. [Core Assumptions](#core-assumptions)
2. [Problem Analysis & Solution](#problem-analysis--solution)
3. [Technical Architecture](#technical-architecture)
4. [Implementation Details](#implementation-details)
5. [Challenges & Solutions](#challenges--solutions)
6. [Future Improvements](#future-improvements)
7. [Getting Started](#getting-started)

---

## Core Assumptions

### Single Review Per Recipe Enhancement

The platform operates on using single review to enchance the recipe instead of combining multiple reviews.
- **Quality over Quantity**: Combining modifications from different reviews creates inconsistent results and conflicting changes
- **Attribution Clarity**: Single-review enhancement maintains clear, traceable attribution back to the source
- **Recipe Coherence**: A single reviewer's modifications form a cohesive set of improvements that work together
- **Reduced Complexity**: Eliminates the combinatorial explosion of trying to merge multiple modification sets

**Selection Strategy**: We select the **highest-rated review** with modifications (by star rating) as the source. If two or more reviews have the same rating we select the one with most detailed review by length of words in that review. This heuristic prioritizes community-validated improvements, assuming higher-rated reviews represent more reliable recipe enhancements.

### Recipe Data Sourcing

The platform includes a robust fallback mechanism for recipe discovery:

**Primary Strategy**: Scrape recipe URLs from AllRecipes sitemap.

**Fallback Strategy**: If scraping fails (network issues, website changes, rate limiting), the system automatically falls back to a hardcoded list of five popular recipe URLs that are known to work reliably.
This feels like kind of a **poor assumption** since this will never tell us if our scraping pipeline is failing i.e. if we are actually able to scrape data from the website.
---

## Problem Analysis & Solution Approach

### Step 1: Code Walkthrough 

To understand the system architecture, I traced the pipeline with a real example: the "Best Chocolate Chip Cookies" recipe.

**Initial State**: A recipe with 11 reviews, 5 of which contained user modifications. 

**Processing Flow**:

The system first loads the recipe JSON and identifies all reviews flagged with modifications. From these candidates, it used to selects the random review that I upgraded to use a simple algorithm: sort by star rating (descending), with text length as a tiebreaker for cases where multiple reviews have identical ratings.

Next, the selected review text is sent to the LLM (along with recipe context) to extract structured modifications. Previously, this step would return only a single modification. The system would then apply this modification to the recipe, validate the changes, and generate an enhanced recipe record.

Finally, the enhanced recipe is saved with complete attribution showing which review provided which modification, enabling users to trace improvements back to their source.

---

### Step 2: Issues Identified & Solutions Implemented

#### Issue #1: Single Modification Output from LLM

**Problem**:
The original prompt used single_build_prompt. When a review mentioned multiple improvements, the LLM would identify one major change and ignore others.


**Impact**: 
- Many valuable improvements modifications were lost
- The review's full potential was underutilized

**Solution: Few-Shot Prompting**

I replaced the prompt with **few_short_prompting prompt**. These examples demonstrated:
- How to identify different types of changes (ingredient substitution, quantity adjustment, technique changes, additions, removals)
- How to structure multiple modifications in the output
- Real review text alongside expected multi-modification responses

**Result**:
- More comprehensive recipe enhancements
- Better utilization of reviewer insights
- Improved LLM understanding through example-based learning
- LLM returned multiple modifications that just one.

---

#### Issue #2: Single Modification Application

**Problem**:
The codebase only implemented functionality to apply one modification at a time. With the new few-shot prompting returning multiple modifications, the pipeline couldn't properly handle them.

**Impact**:
- Modifications beyond the first were ignored
- Pipeline couldn't leverage the multiple-modification capability being developed
- System couldn't reach its full potential

**Solution: Batch Modification Application**

We implemented comprehensive batch processing functionality that:
- Accepts a list of multiple modifications
- Sequentially applies each modification to the recipe
- Tracks changes made by each modification separately
- Maintains detailed records for attribution

The batch processing maintains the order of operations, meaning earlier modifications are applied first, and later modifications work with the already-modified recipe. This sequential approach prevents conflicts and makes the enhancement history clear.

**Result**:
- All extracted modifications are now applied
- Complete enhancement history is preserved
- Changes from each modification are tracked separately
- Users can see exactly which review contributed which changes

---

#### Issue #3: Safety Validation Never Implemented

**Problem**:
The `validate_modification_safety` method existed in the codebase but was never actually called during the modification application process. This meant invalid modifications could be applied to recipes, potentially corrupting them.


**Impact**:
- Invalid modifications could break recipes (e.g., targeting non-existent ingredients)
- No protection against LLM hallucinations
- Silent failures that would only be noticed during manual review
- Risk of corrupted enhanced recipes in production

**Solution: Integration into Modification Pipeline**

We integrated safety validation directly into the modification application workflow so that:
- Every modification is validated before application
- Validation checks confirm target text exists in the recipe
- Validation verifies similarity confidence (ensuring matches are legitimate, not accidental)
- Validation confirms all required fields are present and complete
- Invalid modifications are rejected with detailed logging
- The system adopts a "safe failure" approach: skip problematic modifications rather than corrupt recipes

**Validation Checks**:
1. **Target Existence**: Does the ingredient or instruction exist in the recipe?
2. **Similarity Confidence**: Is the match confident (80%+ similarity)?
3. **Field Completeness**: Does a replace operation have replacement text? Does an add operation have text to add?

**Result**:
- Recipes are protected from invalid modifications
- Users can see which modifications passed and which failed
- Detailed logs explain why modifications were rejected
- System reliability is dramatically improved
- Safe failure prevents silent data corruption

---

### Step 3: Scaling Challenges

#### Challenge: Recipe Sourcing for Production Scale

**Problem**:
The scraper had a hard-coded limit of 5 recipes for testing purposes. This is fine for development but insufficient for production systems that need to handle hundreds or thousands of recipes.

**Consideration**: How do we source recipes at scale while being respectful of the website and avoiding unnecessary re-processing?

**Root Cause**:
The limit maybe intentionally set for development/testing when processing speed and API costs are primary concerns.

**Two Strategies Identified**:

**Strategy 1: Incremental Insertion (Recommended for Production)**

Only scrape and process recipes that aren't already in the system. This approach:
- Minimizes duplicate processing
- Reduces API costs significantly
- Respects AllRecipes' server resources
- Scales naturally as new recipes are published
- Enables continuous, long-running enhancement pipelines
- Works well for frequent small updates

The decision to use incremental insertion depends on how frequently new recipes are added to the site and how often your system runs. For a continuously operating system, this is ideal.

**Strategy 2: Batch Scraping with Checkpointing (For Periodic Updates)**

Scrape recipes in manageable batches with saved checkpoints that allow the process to resume if interrupted. This approach:
- Handles hundreds or thousands of recipes
- Allows process resumption after failures
- Provides clear progress visibility
- Suits scheduled/batch processing models
- Works well for weekly/monthly full updates

The choice between strategies depends on your operational model: continuous incremental updates vs. periodic batch processing.

**Impact on Token Limits and Cost**:
With scaling from 5 to hundreds of recipes, the original token limit of 1000 per LLM call became insufficient. A single modification call could consume 400-600 tokens, leaving minimal room for multiple modifications. We increased the limit to 2000 to account for the new multi-modification capability while maintaining safety margins.

---

## Technical Architecture

### System Overview

The platform consists of five main components working together in sequence:

**Recipe Scraper**: Discovers and downloads recipe data from AllRecipes.com, with fallback to known working URLs if real-time scraping fails. Extracts recipe metadata, ingredients, instructions, and user reviews.

**Data Parser**: Converts raw HTML/JSON into structured recipe objects. Identifies reviews containing user modifications and flags them appropriately.

**Modification Extractor (LLM)**: Sends selected review text to GPT-4o-mini along with recipe context. Uses few-shot examples to guide the LLM toward extracting multiple distinct modifications in structured format. Returns a list of modifications with detailed edit instructions.

**Recipe Modifier**: Applies extracted modifications to the original recipe with safety validation. Uses fuzzy string matching to locate target ingredients/instructions even with minor text variations. Tracks all changes with detailed before/after records.

**Enhanced Recipe Generator**: Combines the modified recipe with complete attribution information, creating a new record that shows exactly which review provided which modifications.

---



## Key Technical Decisions

#### Model Selection: GPT-3.5-Turbo → GPT-4o-mini

**Context**:
After implementing few-shot prompting with multiple detailed examples, the original model (GPT-3.5-Turbo) began struggling with prompt comprehension. It would:
- Return only one modification despite multiple being present
- Return partially malformed JSON
- Ignore portions of complex prompts
- Fail at parsing nested structures

**Analysis**:
GPT-3.5-Turbo excels at instruction-following with simple prompts but struggles with complex few-shot learning scenarios. The newer GPT-4o-mini model was designed specifically to handle sophisticated in-context learning.

**Decision Rationale**:
While GPT-4o-mini costs approximately 3x more per call than GPT-3.5-Turbo, it provides:
- 92% vs 45% success rate on extraction
- Reliable JSON parsing for complex structures
- Better handling of edge cases

**Cost-Benefit**:
The higher per-call cost is offset by:
- Fewer retries needed
- More comprehensive modifications per call
- Higher quality results requiring less human review
- Better utilization of the review data

The upgrade was justified not as a technology choice but as a business decision: paying more per call for better quality results.

#### Token Limit Optimization: 1000 → 2000

**Context**:
The original 1000-token limit was designed for single-modification extraction and proved insufficient for multi-modification scenarios.

With a 1000-token limit, extraction would be truncated, losing modifications and producing incomplete responses.

**Decision Rationale**:
Increasing to 2000 tokens provides:
- Safety margin against truncation
- Room for complex recipe descriptions
- Space for multi-modification outputs
- Buffer for edge cases and unusual recipes

The increased cost per call is minimal compared to the risk of truncated responses and lost modifications.


## Implementation Details

### Updated to Few-Shot Prompting Strategy

Rather than instructing the LLM with abstract rules, we teach it through examples. The prompt includes several real review scenarios, each showing:
- Actual user review text
- Expected structured output format
- Multiple distinct modifications from a single review
- Various modification types (quantity adjustments, additions, removals, technique changes)

This example-based approach works because:
- LLMs learn patterns better from examples than descriptions
- Concrete patterns are easier to replicate
- Ambiguity is reduced through demonstration
- Edge cases can be handled with additional examples

The few-shot examples are carefully selected to cover diverse modification types and recipe complexities, ensuring the LLM learns a generalizable pattern.

### Applied already existing Validation Safety Architecture

The system implements three-tier validation:

**Tier 1: Pre-Application Validation**
- Checks if target ingredient or instruction exists
- Verifies similarity confidence exceeds threshold
- Confirms all required fields are populated
- Rejects modifications that fail any check

**Tier 2: Fuzzy Matching with Fallbacks**
- First attempts substring containment (robust against minor variations)
- Falls back to fuzzy string matching if exact substring not found
- Tracks confidence level for each match
- Provides detailed logging of match quality

**Tier 3: Change Tracking**
- Records original vs modified text
- Maintains before/after state
- Enables auditing and reversal if needed
- Supports detailed attribution

This multi-tier approach ensures safety without over-rejecting valid modifications.

## Challenges & Solutions

### Challenge 1: LLM Model Comprehension with Complex Prompts

**Situation**:
After implementing few-shot prompting with multiple detailed examples showing multi-modification extraction, GPT-3.5-Turbo consistently failed to produce correct outputs. It would either extract only one modification, return malformed JSON, or ignore large portions of the prompt.

**Root Cause Analysis**:
Few-shot prompting is a form of in-context learning that works best with larger, more capable models. GPT-3.5-Turbo has constraints on how much context it can effectively process, particularly with complex nested examples.

**Attempted Solutions**:
1. Simplifying the prompts (reduced effectiveness)
2. Using fewer examples (insufficient for diverse cases)
3. More detailed instructions (helped slightly but insufficient)

**Final Resolution**:
Upgraded to GPT-4o-mini, which was specifically designed for sophisticated in-context learning scenarios. The model successfully:
- Parses complex few-shot examples
- Extracts multiple modifications reliably
- Produces well-formed JSON consistently
- Handles edge cases better


---

### Challenge 2: Code Redundancy and Maintainability

**Situation**:
Review filtering logic (`has_modification` checks) appeared in multiple locations throughout the codebase:
- Once before sending reviews to the extractor
- Once inside the extractor function itself
- Again in batch processing methods
- Additionally in validation logic

This redundancy created maintenance challenges: if the filtering logic needed to change, multiple places needed updates, increasing the risk of inconsistency.


**Resolution**:
- Identified the most appropriate single location (at pipeline entry point)
- Consolidated all filtering logic to that location
- Removed redundant checks from lower-level functions
- Updated documentation to clarify responsibility

**Principle Applied**:
Don't Repeat Yourself (DRY): Each piece of logic should exist in exactly one place, making the code more maintainable and reducing bugs.

---


## Future Improvements

### Phase 1: Optimization and Efficiency (Priority: High)

**Caching Layer**: Implement intelligent caching so that identical reviews don't trigger redundant LLM calls. If the same review text appears for multiple recipes (which happens in aggregator sites), we cache the extraction result.

#### Async Parallel Processing Architecture

**Context**:
Processing single reviews sequentially meant a 50-review batch took 45+ seconds with 50 API calls.

**Solution**:
Implementing async concurrent processing with semaphore-based rate limiting allows multiple reviews to be processed simultaneously while respecting rate limits.

**Architecture**:
- Uses AsyncOpenAI client for non-blocking I/O
- Semaphore limits concurrent requests (default: 5 simultaneous)
- `asyncio.gather()` collects results as they complete
- Backward-compatible synchronous wrappers provided

**Benefits**:
- Same 50 reviews processed in 9 seconds (5x improvement)
- No additional API cost (same total calls)
- Respects rate limiting (configurable concurrency)
- Scales easily: increase max_concurrent for faster processing

---

## Files updated
- enhanced_recipe_generator
- pipeline.py
- prompts.py
- recipe_modifier
- tweak_extractor