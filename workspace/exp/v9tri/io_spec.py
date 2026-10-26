"""Typed I/O specification for TRIAD-PACT evidence.

The protocol is deliberately small.  A producer may submit *evidence* for
one horizon; the bus checks the evidence against the instance, updates the
monotone bracket, and refuses any message that would make the bracket
inconsistent.  The bus never trusts a producer's `certified` flag, and the
certificate is reconstructed from the stored evidence only.

Wire types
----------
Evidence(kind, h, proof, schedule, machine, cmax, probe_id, scope)
    kind = NO  : proof is an auditable NO(h) proof
    kind = YES : (schedule, machine) is checked and Cmax <= h
    kind = UNK : no payload; a probe that did not decide h

TriangulationCertificate(vertices, L0, U0, initial, L, U, schedule,
                         machine, lb_proof)
    vertices are strictly increasing in h and normalized to be inside
    (L, U) for UNK vertices.  NO/YES vertices may lie outside the current
    open interval because they are what closes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import hashlib
import json


NO = 'NO'
YES = 'YES'
UNK = 'UNK'
KINDS = (NO, YES, UNK)


def instance_scope(inst: dict) -> str:
    """A stable, content-based scope for an instance."""
    payload = json.dumps(
        [inst.get('n'), inst.get('m'), inst.get('p'),
         inst.get('pred'), inst.get('elig')], sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def cmax(inst: dict, starts) -> int:
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


@dataclass
class Evidence:
    kind: str
    h: int
    proof: Any = None
    schedule: Optional[list] = None
    machine: Optional[list] = None
    cmax: Optional[int] = None
    probe_id: int = 0
    lp: int = 0
    scope: str = ''
    meta: dict = field(default_factory=dict)

    def audit(self, inst: dict, scope: Optional[str] = None) -> bool:
        try:
            if self.kind not in KINDS or not isinstance(self.h, int):
                return False
            if scope is not None and self.scope not in ('', scope):
                return False
            if self.kind == NO:
                return bool(self.proof is not None
                            and self.proof.h == self.h
                            and self.proof.audit_rdf())
            if self.kind == YES:
                if self.schedule is None or self.machine is None:
                    return False
                from rdf import check_schedule
                c = cmax(inst, self.schedule)
                return bool(c <= self.h
                            and check_schedule(inst, c, self.schedule,
                                               self.machine))
            # UNK must not carry evidence.
            return (self.proof is None and self.schedule is None
                    and self.machine is None and self.cmax is None)
        except Exception:
            return False

    def wire(self) -> dict:
        return dict(kind=self.kind, h=self.h,
                    proof_kind=getattr(self.proof, 'kind', None),
                    proof_h=getattr(self.proof, 'h', None),
                    schedule=(None if self.schedule is None
                              else [int(x) for x in self.schedule]),
                    machine=(None if self.machine is None
                             else [int(x) for x in self.machine]),
                    cmax=self.cmax, probe_id=self.probe_id,
                    lp=self.lp, scope=self.scope)


class TriangulationCertificate:
    """A bracket plus a triangulated history of probes on the h-axis."""

    kind = 'triad-cert'

    def __init__(self, inst, L0, U0, initial, vertices, L, U,
                 schedule, machine, lb_proof, scope=None):
        self.inst = inst
        self.L0 = int(L0)
        self.U0 = int(U0)
        self.initial = initial
        self.vertices = list(vertices or [])
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.lb_proof = lb_proof
        self.scope = scope if scope is not None else instance_scope(inst)

    # ------------------------------------------------------------- audit
    def _expected_bounds(self):
        L, U = self.L0, self.U0
        best_no = None
        best_yes = None
        for ev in self.vertices:
            if ev.kind == NO:
                if ev.h + 1 > L:
                    L = ev.h + 1
                    best_no = ev
            elif ev.kind == YES:
                c = ev.cmax if ev.cmax is not None else cmax(
                    self.inst, ev.schedule)
                if c < U:
                    U = c
                    best_yes = ev
        return L, U, best_no, best_yes

    def audit_rdf(self, require_final=False) -> bool:
        try:
            if not self.initial.audit(self.inst, self.scope):
                return False
            if self.initial.kind != NO:
                return False
            if self.initial.h != self.L0 - 1:
                return False
            seen = set()
            for ev in self.vertices:
                if ev.h in seen:
                    return False
                seen.add(ev.h)
                if ev.h < self.L0 - 1 or ev.h > self.U0:
                    return False
                if not ev.audit(self.inst, self.scope):
                    return False
            L, U, best_no, best_yes = self._expected_bounds()
            if (L, U) != (self.L, self.U):
                return False
            if L > U:
                return False
            # The stored lower proof is exactly the proof at L-1.
            if L > self.L0:
                if best_no is None or best_no.h != L - 1:
                    return False
                if self.lb_proof is not best_no.proof:
                    return False
            else:
                if self.lb_proof is not self.initial.proof:
                    return False
            if self.lb_proof is None or self.lb_proof.h != L - 1:
                return False
            if not self.lb_proof.audit_rdf():
                return False
            # The stored upper schedule is the best schedule.
            if self.schedule is None or self.machine is None:
                return False
            c = cmax(self.inst, self.schedule)
            if c != U:
                return False
            from rdf import check_schedule
            if not check_schedule(self.inst, c, self.schedule,
                                  self.machine):
                return False
            # Normalization: UNK vertices are strictly inside (L, U).
            for ev in self.vertices:
                if ev.kind == UNK and not (L < ev.h < U):
                    return False
            if require_final and L != U:
                return False
            return True
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()

    def wire(self) -> dict:
        return dict(kind=self.kind, L0=self.L0, U0=self.U0, L=self.L,
                    U=self.U, scope=self.scope,
                    lb_kind=getattr(self.lb_proof, 'kind', None),
                    initial=self.initial.wire(),
                    vertices=[ev.wire() for ev in self.vertices],
                    schedule=(None if self.schedule is None
                              else [int(x) for x in self.schedule]),
                    machine=(None if self.machine is None
                             else [int(x) for x in self.machine]))


class EvidenceBus:
    """Strict in-process realization of the TRIAD I/O contract.

    The bus owns the bracket.  A producer can only submit one Evidence at
    a time; the bus checks the type, the scope, and the semantic payload,
    then applies the monotone update.  Invalid messages are rejected with
    a reason and leave the state unchanged.
    """

    def __init__(self, inst, L0, U0, initial, schedule, machine,
                 scope=None):
        self.inst = inst
        self.L0, self.U0 = int(L0), int(U0)
        self.scope = scope if scope is not None else instance_scope(inst)
        self.initial = initial
        self.schedule = list(schedule)
        self.machine = list(machine)
        self.base_schedule = list(schedule)
        self.base_machine = list(machine)
        self.L, self.U = int(L0), int(U0)
        self.lb_proof = initial.proof
        self.vertices = {}
        self.log = []
        self.rejected = []

    def _bounds(self):
        L, U = self.L0, self.U0
        no = None
        yes = None
        for h, ev in sorted(self.vertices.items()):
            if ev.kind == NO and h + 1 > L:
                L, no = h + 1, ev
            if ev.kind == YES:
                c = ev.cmax
                if c < U:
                    U, yes = c, ev
        return L, U, no, yes

    def _rebuild(self):
        L, U, no, yes = self._bounds()
        self.L, self.U = L, U
        self.lb_proof = (no.proof if no is not None
                         else self.initial.proof)
        if yes is not None:
            self.schedule = list(yes.schedule)
            self.machine = list(yes.machine)
        else:
            self.schedule = list(self.base_schedule)
            self.machine = list(self.base_machine)
        # Normalize: UNK outside the open interval is no longer needed.
        for h in list(self.vertices):
            if self.vertices[h].kind == UNK and not (L < h < U):
                del self.vertices[h]

    def submit(self, ev: Evidence) -> tuple[bool, str]:
        before = dict(self.vertices)
        try:
            if not isinstance(ev, Evidence):
                return self._reject('not an Evidence')
            if ev.scope not in ('', self.scope):
                return self._reject('scope mismatch')
            if not isinstance(ev.h, int):
                return self._reject('non-integer h')
            if ev.h < self.L0 - 1 or ev.h > self.U0:
                return self._reject('h outside the root interval')
            if not ev.audit(self.inst, self.scope):
                return self._reject('evidence audit failed')
            if ev.kind in (NO, YES) and ev.h in self.vertices:
                old = self.vertices[ev.h]
                if old.kind != UNK:
                    return self._reject('conflicting evidence at h')
            if ev.kind == UNK:
                if not (self.L < ev.h < self.U):
                    return self._reject('UNK outside the open interval')
                if ev.h in self.vertices:
                    return self._reject('duplicate UNK')
            # Tentatively apply; reject if it makes L > U.
            if ev.kind in (NO, YES):
                self.vertices[ev.h] = ev
            else:
                self.vertices[ev.h] = ev
            self._rebuild()
            if self.L > self.U:
                self.vertices = before
                self._rebuild()
                return self._reject('L > U after update')
            self.log.append(ev.wire())
            return True, 'ok'
        except Exception as exc:
            self.vertices = before
            self._rebuild()
            return self._reject('exception: %s' % exc)

    def _reject(self, why):
        self.rejected.append(why)
        return False, why

    def certificate(self):
        return TriangulationCertificate(
            self.inst, self.L0, self.U0, self.initial,
            list(self.vertices.values()), self.L, self.U,
            self.schedule, self.machine, self.lb_proof,
            scope=self.scope)

    def audit(self, require_final=False):
        return self.certificate().audit_rdf(require_final=require_final)
