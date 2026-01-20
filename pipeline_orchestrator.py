#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP PIPELINE ORCHESTRATOR
==========================
This script demonstrates how to orchestrate the existing modules into a unified
processing pipeline without modifying the original codebases.

It connects:
1. UYAPDosyaAnalyzer (Classification)
2. HacizIhbarAnalyzer (Bank Responses)
3. IIK106110Takip (Legal Deadlines)
4. NeatPDFUretici (Conversion)

Usage:
    python3 pipeline_orchestrator.py
"""

import os
import shutil
import tempfile
import json
from datetime import datetime
from dataclasses import asdict

# Import existing modules
try:
    from uyap_dosya_analyzer import UYAPDosyaAnalyzer, EvrakKategorisi, HacizTuru
    from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu
    from iik_106_110_takip import IIK106110Takip, MalTuru
    from neat_pdf_uretici import NeatPDFUretici
    MODULES_OK = True
except ImportError as e:
    print(f"❌ Critical modules missing: {e}")
    MODULES_OK = False

class PipelineManager:
    def __init__(self):
        if not MODULES_OK:
            raise RuntimeError("Required modules not found.")

        self.uyap = UYAPDosyaAnalyzer()
        self.banka = HacizIhbarAnalyzer()
        self.takip = IIK106110Takip()
        self.pdf = NeatPDFUretici()

        # Unified State
        self.state = {
            "processed_files": [],
            "banka_cevaplari": [],
            "haciz_takip": [],
            "tebligatlar": [],
            "errors": []
        }

    def process_pipeline(self, source_path: str):
        """
        Executes the full data pipeline:
        Ingest -> Convert -> Classify -> Analyze -> Report
        """
        print(f"🚀 Starting Pipeline for: {source_path}")

        # 1. Ingestion & Conversion Layer
        work_dir = tempfile.mkdtemp()
        try:
            files = self._ingest_and_convert(source_path, work_dir)

            # 2. Classification & Routing Layer
            for file_path in files:
                self._process_single_file(file_path)

            # 3. Synthesis Layer
            return self._generate_master_report()

        finally:
            shutil.rmtree(work_dir)

    def _ingest_and_convert(self, source, work_dir):
        """Extracts ZIPs and converts UDFs to readable formats."""
        processed_files = []

        # Extract if ZIP
        if source.endswith('.zip'):
            # Logic to extract (simplified)
            # In a real scenario, use zipfile to extract to work_dir
            pass

        # For demonstration, we assume source is a file list or dir
        # If it's a UDF, convert to PDF first
        if source.endswith('.udf'):
            pdf_path = source + ".pdf"
            self.pdf.uret(source, pdf_path)
            processed_files.append(pdf_path)
        else:
            processed_files.append(source)

        return processed_files

    def _process_single_file(self, file_path):
        """Orchestrates logic based on file type."""
        filename = os.path.basename(file_path)

        # Step A: Classify using UYAP Analyzer
        # We access the internal classification logic for granular control
        # (Assuming file content reading logic exists here)
        with open(file_path, 'r', errors='ignore') as f:
            content = f.read(1000) # Read header

        doc_type = self.uyap._siniflandir_evrak(filename, content)
        print(f"📄 Classified {filename} -> {doc_type.value}")

        # Step B: Route to Specialized Analyzers

        # Route 1: Bank Responses
        if doc_type == EvrakKategorisi.BANKA_CEVABI:
            with open(file_path, 'r', errors='ignore') as f:
                full_text = f.read()

            result = self.banka.analyze_response(full_text)
            self.state["banka_cevaplari"].append({
                "file": filename,
                "bank": result.muhatap_adi,
                "status": result.cevap_durumu.value,
                "amount": result.bloke_tutari
            })

        # Route 2: Liens (Haciz) -> Legal Deadline Tracker
        elif doc_type == EvrakKategorisi.HACIZ_IHBAR:
            # Extract date (Mock logic)
            # In production, use regex from UYAPDosyaAnalyzer
            date = datetime.now() # Placeholder

            # Determine Asset Type
            mal_turu = MalTuru.TASINIR_DIGER
            if "taşınmaz" in content.lower(): mal_turu = MalTuru.TASINMAZ

            # Feed to Tracker
            record = self.takip.ekle(
                mal_turu=mal_turu,
                haciz_tarihi=date,
                mal_aciklamasi=filename
            )

            self.state["haciz_takip"].append({
                "file": filename,
                "deadline": record.son_tarih.strftime('%Y-%m-%d'),
                "days_left": record.kalan_gun
            })

    def _generate_master_report(self):
        """Aggregates intelligence from all modules."""
        report = {
            "summary": {
                "total_files": len(self.state["processed_files"]),
                "blocked_amount": sum(x['amount'] for x in self.state["banka_cevaplari"]),
                "critical_deadlines": len([x for x in self.state["haciz_takip"] if x['days_left'] < 30])
            },
            "details": self.state
        }
        return json.dumps(report, indent=4, ensure_ascii=False)

# === DEMONSTRATION ===
if __name__ == "__main__":
    print("🔧 Initializing Data Orchestration Pipeline...")
    if MODULES_OK:
        orchestrator = PipelineManager()
        print("✅ Pipeline System Ready.")
        print("ℹ️  To execute, instantiate PipelineManager and call process_pipeline(path)")
        print("   This architecture allows scaling without modifying core analyzers.")
