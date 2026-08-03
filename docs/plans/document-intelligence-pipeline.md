# Nemotron OCR + Nemotron Page Elements
## Architecture & Best Practices
Version 1.0

---

# Objective

Design a production-grade document intelligence platform using NVIDIA's Nemotron ecosystem.

The architecture should support:

- OCR
- Document layout understanding
- Table extraction
- Chart understanding
- Semantic search
- RAG
- Agentic workflows
- Knowledge Graph construction
- Insurance, finance and enterprise document processing

This document is intended as implementation guidance for Claude Code.

---

# High Level Architecture

```text
                  PDF

                   │

           FastAPI Upload API

                   │

          Prefect Flow Engine

                   │

           Split Into Pages

                   │

        Nemotron Page Elements

                   │

      ┌────────────┼────────────┐
      │            │            │
      ▼            ▼            ▼

    OCR         Tables       Figures

      │            │            │
      └────────────┼────────────┘
                   │

         Structured Document

                   │

        Semantic Chunk Builder

                   │

            Embedding Engine

                   │

         Vector Database

                   │

          Knowledge Graph

                   │

           AI Agent Layer

                   │

      Underwriter / Analyst UI
```

---

# Philosophy

Traditional OCR treats documents as text.

Modern document AI treats documents as structured knowledge.

Never flatten documents into text until absolutely necessary.

Instead preserve

- pages
- regions
- tables
- figures
- coordinates
- metadata
- reading order

Everything downstream becomes easier.

---

# Nemotron Components

## Nemotron Page Elements

Purpose:

Understand document layout.

Outputs:

- title
- paragraph
- table
- chart
- image
- figure
- footer
- header

Each includes

- confidence
- bounding box

No OCR occurs here.

Think of this as computer vision for documents.

---

## Nemotron OCR

Purpose:

Read text.

Input

Usually cropped regions produced by Page Elements.

Output

- text
- confidence
- reading order

---

## Nemotron Table Structure

Purpose

Convert detected tables into structured data.

Instead of

```
| 123 | ABC |
```

Generate

```json
{
  "rows":[...],
  "columns":[...]
}
```

This becomes queryable.

---

## Vision Models

Charts

Infographics

Engineering drawings

should NOT be OCR'd.

Instead send them to a VLM.

---

# Page Processing Pipeline

For every page

```
Page

↓

Page Elements

↓

Regions

↓

OCR

↓

Merge

↓

Structured JSON
```

Never OCR the entire page if regions have already been identified.

---

# Recommended Data Model

```python
Document

Metadata

Pages

Page

Elements

OCR Blocks

Tables

Figures

Charts

Captions

Embeddings

Knowledge Graph IDs
```

---

# Bounding Boxes

Always preserve coordinates.

```python
BoundingBox

x_min

y_min

x_max

y_max
```

Bounding boxes enable

- highlighting
- citations
- review
- audit trails
- answer provenance

Never discard them.

---

# Reading Order

Preserve

```
Page

↓

Blocks

↓

Paragraphs

↓

Lines

↓

Words
```

Reading order matters for

contracts

insurance

scientific papers

legal documents

---

# Parallel Processing

Never process PDFs serially.

Instead

```
PDF

↓

Split Pages

↓

GPU Workers

↓

Merge
```

Then

```
Each Page

↓

Split Regions

↓

Parallel OCR
```

This dramatically increases throughput.

---

# Retry Strategy

Retry pages.

Never retry the entire document.

```
OCR

↓

Validation

↓

Failed Pages

↓

Retry Queue
```

---

# OCR Confidence

Every OCR block should contain

```python
text

confidence

bbox

page

language

rotation
```

Low confidence blocks may be

- human reviewed

or

- rerun

---

# Structured JSON Output

Example

```json
{
  "page":1,
  "elements":[
    {
      "type":"heading",
      "bbox":{},
      "text":"Executive Summary"
    },
    {
      "type":"table",
      "bbox":{}
    }
  ]
}
```

---

# Semantic Chunking

Never chunk by

1000 characters.

Instead

Chunk by

- headings

- paragraphs

- sections

- tables

- figures

This produces much better retrieval.

---

# Storage

Store separately

Original PDF

↓

Original Images

↓

OCR JSON

↓

Tables

↓

Embeddings

↓

Metadata

↓

Knowledge Graph

Never merge everything into one blob.

---

# Suggested Pydantic Models

```python
BoundingBox

PageElement

OCRBlock

Paragraph

Table

Figure

Chart

Page

Document
```

Each model should be versioned.

---

# FastAPI Responsibilities

Upload

Authentication

Validation

Job Creation

Webhook callbacks

Streaming status

No heavy OCR inside FastAPI.

---

# Prefect Responsibilities

Split PDF

Schedule GPU workers

Retry failures

Merge outputs

Generate embeddings

Persist metadata

Launch agents

---

# GPU Workers

Worker 1

Page Elements

Worker 2

OCR

Worker 3

Tables

Worker 4

Vision

Workers remain stateless.

---

# Database

Postgres

Stores

metadata

OCR

jobs

documents

Supabase

provides

API

Auth

Storage

Realtime

---

# Object Storage

Cloudflare R2

or

S3

Store

PDF

Images

Thumbnails

Intermediate crops

Never store binaries inside Postgres.

---

# Vector Database

Options

pgvector

Milvus

Qdrant

Weaviate

Store

semantic chunks

not

entire documents.

---

# Knowledge Graph

Recommended entities

Document

Page

Section

Paragraph

Table

Figure

Policy

Claim

Customer

Broker

Property

Coverage

Underwriter

Relationships become

queryable.

---

# Example Insurance Flow

Submission arrives

↓

PDF uploaded

↓

Page Elements

↓

OCR

↓

Table Extraction

↓

Policy Detection

↓

Knowledge Graph

↓

LLM Summary

↓

Underwriter Review

↓

Decision Support

---

# AI Agents

Suggested agents

Document Intake

OCR QA

Table Validator

Metadata Extractor

Entity Resolver

Knowledge Graph Builder

Embedding Builder

RAG Agent

Policy Reviewer

Fraud Agent

Each agent consumes structured objects.

Not raw text.

---

# Future Enhancements

Handwriting

Mathematics

Engineering Drawings

CAD

GIS

Medical Images

Video Frames

Email Threads

All can reuse the same document abstraction.

---

# Core Principle

Documents are not text.

Documents are structured graphs.

OCR is only one stage.

The real product is a semantic document graph that powers search, RAG, workflow automation, and AI agents.