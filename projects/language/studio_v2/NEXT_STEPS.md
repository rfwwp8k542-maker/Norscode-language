# Studio v2 Next Steps

Studio v2 already has the foundation, AI flow, stabilization, and a GUI shell.
This note turns the next round of work into a practical priority list.

## Current goal

Make Studio v2 feel like a daily-use IDE:

- open a project and restore state
- edit files comfortably
- navigate symbols quickly
- keep AI helpful, optional, and preview-first
- stay fast on larger projects

## Progress so far

The first memory milestone is now implemented:

- project sessions
- recent projects
- restore last active file
- save workspace state

That means Studio v2 can remember a workspace between runs and reopen it with
useful context.

## In progress

The next milestone has started:

- tabs and split views
- search and replace

## Priority order

### 1. Project sessions

Goal:
- open a project and remember it next time
- store last active file, window state, and recent projects
- add autosave and crash recovery

Done when:
- Studio v2 can reopen the same project with the same context
- users do not need to reconfigure their layout every time

### 2. Editor power-ups

Goal:
- tabs and split views
- search and replace
- go-to-line
- go-to-symbol
- rename with preview
- select all references

Done when:
- common editing tasks can be done without leaving the editor shell

### 3. Workspace intelligence

Goal:
- incremental file index
- automatic refresh when files change
- cross-file symbol lookup
- better definitions and references

Done when:
- large projects feel navigable instead of flat

### 4. AI usefulness

Goal:
- explain code
- summarize file or selection
- suggest refactors
- generate tests
- preview patches with accept/reject

Done when:
- AI helps without making changes directly
- the user can always inspect and approve the result

### 5. Performance

Goal:
- lazy-load large projects
- reuse workspace snapshots
- update only changed parts
- avoid unnecessary full reloads

Done when:
- startup stays quick on bigger repos
- navigation remains responsive

### 6. UI polish

Goal:
- clearer panel layout
- better status bar
- more keyboard shortcuts
- theme options
- better empty states

Done when:
- the app feels coherent and calm during daily use

### 7. Diagnostics and test flow

Goal:
- run tests for active file
- run project test suites
- show clickable diagnostics
- surface status inline

Done when:
- issues are visible immediately inside the app

## Next milestone

The next most useful increment is more editor power:

1. go-to-line
2. go-to-symbol
3. rename with preview
4. select all references
5. tab switching
6. split focus switching

That gives Studio v2 the editing ergonomics to feel like a real daily IDE.
