# Agent DevTools

## Goal

Build debugging tools for computer-use agents.

## Problem

When an agent fails, developers often cannot clearly see which action failed or why.

## MVP

Record one computer action with:

- Action type and arguments
- Screenshot before and after
- Start time and duration
- Success or failure
- Failure reason

## First Demo

Record a browser click and display its complete action trace.

## Non-Goals

- Building a complete agent
- Training a model
- Automatic recovery
- Supporting every platform
- Complex dashboard

## Success Criteria

A developer can inspect a failed action and understand what happened.