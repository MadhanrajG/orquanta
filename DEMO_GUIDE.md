# OrQuanta Demo Quick Reference

## Pre-Demo Checklist (2 minutes before client joins)

```powershell
# 1. Reset to clean state
.\DEMO.ps1

# 2. Open browser
start http://localhost:8000/docs

# 3. Have terminal ready
python DEMO_SCRIPT.py
```

---

## The Golden Line (Memorize This)

> **"The system learned from a real failure, improved its behavior automatically, and still allows full human rollback."**

Say this after Step 4. Pause. Let them react.

---

## Demo Flow (3 minutes total)

| Step | Time | What to Show | What to Say |
|------|------|--------------|-------------|
| 1 | 30s | Policy v1 (cost-focused) | "System is currently cost-focused" |
| 2 | 30s | Submit 80GB job → T4 | "It recommended the cheapest option—this will fail" |
| 3 | 45s | Policy evolves to v2 | "System learned and updated its policy" |
| 4 | 30s | Same job → H100 | **[THE GOLDEN LINE]** |
| 5 | 30s | Rollback to v1 | "Every decision is reversible" |

**Total: 2m 45s + questions**

---

## What NOT to Say

❌ "This is just a demo"  
✅ "This is the production API"

❌ "We plan to add..."  
✅ "v1 is scoped. We expand based on usage."

❌ "It's autonomous AI"  
✅ "It learns safely with full human control"

---

## If They Ask...

**"Can it handle our workload?"**  
→ "What's your typical VRAM requirement? OrQuanta learns from your actual patterns."

**"How does it compare to [competitor]?"**  
→ "Most tools use static rules. OrQuanta learns from real outcomes."

**"What if it makes a bad decision?"**  
→ "Instant rollback to any previous version. Every decision is versioned."

**"When can we try it?"**  
→ "Internal alpha is ready now. 2-week pilot, then we decide on v2 scope together."

---

## Close Strong

**Final Statement:**
> "v1 is intentionally scoped: single policy, simulation-based learning, internal deployment. We expand only based on real usage. That's engineering discipline."

**Then ask:**
> "What's the next step you'd like to see?"

---

## Emergency Fallback

If demo breaks:
1. Show `LAUNCH_REPORT.md` (validation results)
2. Show `README.md` (architecture)
3. Say: "The system passed 24 automated tests. Let me show you the verification."

---

## Post-Demo

**If positive:**
- Schedule 2-week pilot
- Define success metrics
- Agree on feedback cadence

**If neutral:**
- Ask: "What would make this valuable for your team?"
- Document specific requirements
- Follow up in 1 week

**If negative:**
- Thank them for their time
- Ask: "What would you build differently?"
- Learn and iterate

---

**You're ready. Go show them decision intelligence.** 🦅
