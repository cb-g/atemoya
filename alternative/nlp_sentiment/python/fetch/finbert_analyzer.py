#!/usr/bin/env python3
"""
FinBERT-based sentiment analyzer for Discord messages.

Uses ProsusAI/finbert for financial sentiment classification.
Provides more accurate sentiment than rule-based keyword matching.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification


# FinBERT model - fine-tuned BERT for financial sentiment
MODEL_NAME = "ProsusAI/finbert"

# Sentiment labels from FinBERT
LABEL_MAP = {
    0: "positive",
    1: "negative",
    2: "neutral",
}

# Score mapping for aggregation
SCORE_MAP = {
    "positive": 1.0,
    "negative": -1.0,
    "neutral": 0.0,
}


@dataclass
class SentimentResult:
    """Result from FinBERT sentiment analysis."""
    label: str  # positive, negative, neutral
    score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    probabilities: dict[str, float]  # Full probability distribution


class FinBERTAnalyzer:
    """
    FinBERT-based sentiment analyzer for financial text.

    Usage:
        analyzer = FinBERTAnalyzer()
        result = analyzer.analyze("AAPL is looking bullish after earnings")
        print(result.label, result.score, result.confidence)
    """

    def __init__(self, device: Optional[str] = None, cache_dir: Optional[str] = None):
        """
        Initialize FinBERT analyzer.

        Args:
            device: Device to use ('cuda', 'mps', 'cpu'). Auto-detected if None.
            cache_dir: Directory to cache model weights.
        """
        # Auto-detect device
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        self.device = device
        print(f"FinBERT: Loading model on {device}...")

        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            cache_dir=cache_dir,
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_NAME,
            cache_dir=cache_dir,
        ).to(device)

        self.model.eval()
        print("FinBERT: Model loaded successfully")

    def analyze(self, text: str) -> SentimentResult:
        """
        Analyze sentiment of a single text.

        Args:
            text: Text to analyze

        Returns:
            SentimentResult with label, score, and confidence
        """
        # Tokenize
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        ).to(self.device)

        # Inference
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)[0]

        # Get prediction
        pred_idx = probs.argmax().item()
        label = LABEL_MAP[pred_idx]
        confidence = probs[pred_idx].item()

        # Build probability dict
        probabilities = {
            LABEL_MAP[i]: probs[i].item()
            for i in range(len(LABEL_MAP))
        }

        # Calculate continuous score (-1 to 1)
        # Weighted by probabilities: positive contributes +1, negative -1, neutral 0
        score = probabilities["positive"] - probabilities["negative"]

        return SentimentResult(
            label=label,
            score=score,
            confidence=confidence,
            probabilities=probabilities,
        )

    def analyze_batch(
        self,
        texts: list[str],
        batch_size: int = 16,
        show_progress: bool = True,
    ) -> list[SentimentResult]:
        """
        Analyze sentiment of multiple texts efficiently.

        Args:
            texts: List of texts to analyze
            batch_size: Batch size for inference
            show_progress: Show progress bar

        Returns:
            List of SentimentResult objects
        """
        results = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]

            if show_progress:
                batch_num = i // batch_size + 1
                print(f"  Processing batch {batch_num}/{total_batches}...", end="\r")

            # Tokenize batch
            inputs = self.tokenizer(
                batch_texts,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            ).to(self.device)

            # Inference
            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1)

            # Process each result
            for j, text_probs in enumerate(probs):
                pred_idx = text_probs.argmax().item()
                label = LABEL_MAP[pred_idx]
                confidence = text_probs[pred_idx].item()

                probabilities = {
                    LABEL_MAP[k]: text_probs[k].item()
                    for k in range(len(LABEL_MAP))
                }

                score = probabilities["positive"] - probabilities["negative"]

                results.append(SentimentResult(
                    label=label,
                    score=score,
                    confidence=confidence,
                    probabilities=probabilities,
                ))

        if show_progress:
            print()  # Clear progress line

        return results


def analyze_discord_messages(
    messages_file: str | Path,
    output_file: Optional[str | Path] = None,
    batch_size: int = 16,
    device: Optional[str] = None,
) -> dict:
    """
    Analyze Discord messages with FinBERT.

    Args:
        messages_file: Path to discord_messages.json
        output_file: Output file for results (optional)
        batch_size: Batch size for inference
        device: Device to use

    Returns:
        Dict with analysis results
    """
    messages_file = Path(messages_file)

    # Load messages
    print(f"Loading messages from {messages_file}...")
    with open(messages_file) as f:
        messages = json.load(f)

    print(f"Loaded {len(messages)} messages")

    # Initialize analyzer
    analyzer = FinBERTAnalyzer(device=device)

    # Extract texts
    texts = [m["content"] for m in messages]

    # Analyze
    print(f"\nAnalyzing {len(texts)} messages with FinBERT...")
    results = analyzer.analyze_batch(texts, batch_size=batch_size)

    # Attach results to messages
    for msg, result in zip(messages, results):
        msg["finbert_sentiment"] = {
            "label": result.label,
            "score": result.score,
            "confidence": result.confidence,
            "probabilities": result.probabilities,
        }

    # Aggregate by ticker
    ticker_sentiments = {}
    for msg in messages:
        for ticker in msg.get("tickers_mentioned", []):
            if ticker not in ticker_sentiments:
                ticker_sentiments[ticker] = {
                    "scores": [],
                    "labels": {"positive": 0, "negative": 0, "neutral": 0},
                    "confidences": [],
                }

            fb = msg["finbert_sentiment"]
            ticker_sentiments[ticker]["scores"].append(fb["score"])
            ticker_sentiments[ticker]["labels"][fb["label"]] += 1
            ticker_sentiments[ticker]["confidences"].append(fb["confidence"])

    # Calculate aggregates
    ticker_aggregates = {}
    for ticker, data in ticker_sentiments.items():
        scores = data["scores"]
        ticker_aggregates[ticker] = {
            "ticker": ticker,
            "mention_count": len(scores),
            "avg_score": sum(scores) / len(scores),
            "avg_confidence": sum(data["confidences"]) / len(data["confidences"]),
            "label_distribution": data["labels"],
            "signal": "bullish" if sum(scores) / len(scores) > 0.2 else (
                "bearish" if sum(scores) / len(scores) < -0.2 else "neutral"
            ),
        }

    # Build output
    output = {
        "messages_analyzed": len(messages),
        "model": MODEL_NAME,
        "overall_sentiment": {
            "positive": sum(1 for r in results if r.label == "positive"),
            "negative": sum(1 for r in results if r.label == "negative"),
            "neutral": sum(1 for r in results if r.label == "neutral"),
            "avg_score": sum(r.score for r in results) / len(results),
        },
        "ticker_sentiments": ticker_aggregates,
        "messages": messages,
    }

    # Save if output file specified
    if output_file:
        output_file = Path(output_file)
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nSaved results to {output_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("FINBERT SENTIMENT ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"\nOverall: {output['overall_sentiment']['positive']} positive, "
          f"{output['overall_sentiment']['negative']} negative, "
          f"{output['overall_sentiment']['neutral']} neutral")
    print(f"Average score: {output['overall_sentiment']['avg_score']:.3f}")

    print("\nTop tickers by sentiment:")
    sorted_tickers = sorted(
        ticker_aggregates.values(),
        key=lambda x: x["avg_score"],
        reverse=True,
    )

    print("\n  BULLISH:")
    for t in sorted_tickers[:10]:
        if t["avg_score"] > 0.1:
            print(f"    {t['ticker']}: {t['avg_score']:.3f} ({t['mention_count']} mentions)")

    print("\n  BEARISH:")
    for t in sorted_tickers[-10:]:
        if t["avg_score"] < -0.1:
            print(f"    {t['ticker']}: {t['avg_score']:.3f} ({t['mention_count']} mentions)")

    return output


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze Discord messages with FinBERT sentiment model"
    )
    parser.add_argument(
        "messages_file",
        help="Path to discord_messages.json",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file for results",
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=16,
        help="Batch size for inference (default: 16)",
    )
    parser.add_argument(
        "--device", "-d",
        choices=["cuda", "mps", "cpu"],
        help="Device to use (auto-detected if not specified)",
    )

    args = parser.parse_args()

    analyze_discord_messages(
        messages_file=args.messages_file,
        output_file=args.output,
        batch_size=args.batch_size,
        device=args.device,
    )


def enrich_discord_aggregates(
    aggregates_file: str | Path,
    finbert_analysis_file: str | Path,
    output_file: Optional[str | Path] = None,
) -> dict:
    """
    Enrich rule-based aggregates with FinBERT scores.

    Creates a combined view with both scoring methods.

    Args:
        aggregates_file: Path to discord_aggregates.json (rule-based)
        finbert_analysis_file: Path to finbert_analysis.json
        output_file: Output file for enriched results

    Returns:
        Dict with combined analysis
    """
    aggregates_file = Path(aggregates_file)
    finbert_analysis_file = Path(finbert_analysis_file)

    with open(aggregates_file) as f:
        rule_based = json.load(f)

    with open(finbert_analysis_file) as f:
        finbert = json.load(f)

    finbert_tickers = finbert.get("ticker_sentiments", {})

    # Combine results
    combined = {}
    for ticker, rb_data in rule_based.items():
        rb_score = (
            rb_data["avg_emoji_sentiment"] +
            rb_data["avg_keyword_sentiment"] +
            rb_data["avg_reaction_score"]
        ) / 3

        fb_data = finbert_tickers.get(ticker, {})
        fb_score = fb_data.get("avg_score", 0.0)

        # Weighted combination: 60% FinBERT, 40% rule-based
        # FinBERT is more accurate but rule-based catches emojis/reactions
        if fb_data:
            combined_score = 0.6 * fb_score + 0.4 * rb_score
        else:
            combined_score = rb_score

        # Determine signal
        if combined_score > 0.2:
            signal = "bullish"
        elif combined_score < -0.2:
            signal = "bearish"
        else:
            signal = "neutral"

        combined[ticker] = {
            "ticker": ticker,
            "mention_count": rb_data["mention_count"],
            "unique_authors": rb_data["unique_authors"],
            "rule_based_score": rb_score,
            "finbert_score": fb_score if fb_data else None,
            "combined_score": combined_score,
            "signal": signal,
            "confidence": fb_data.get("avg_confidence", 0.0) if fb_data else 0.0,
            "bullish_count": rb_data["bullish_count"],
            "bearish_count": rb_data["bearish_count"],
            "neutral_count": rb_data["neutral_count"],
            "channels": rb_data["channels"],
            "sample_messages": rb_data["sample_messages"],
        }

    output = {
        "analysis_type": "combined",
        "total_tickers": len(combined),
        "tickers": combined,
    }

    if output_file:
        output_file = Path(output_file)
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Saved combined analysis to {output_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("COMBINED SENTIMENT ANALYSIS (Rule-Based + FinBERT)")
    print("=" * 60)

    sorted_tickers = sorted(
        combined.values(),
        key=lambda x: x["combined_score"],
        reverse=True,
    )

    print("\nBULLISH tickers:")
    for t in sorted_tickers[:10]:
        if t["signal"] == "bullish":
            fb_str = f"{t['finbert_score']:.3f}" if t['finbert_score'] is not None else "N/A"
            print(f"  {t['ticker']}: {t['combined_score']:.3f} "
                  f"(RB: {t['rule_based_score']:.3f}, FB: {fb_str})")

    print("\nBEARISH tickers:")
    for t in reversed(sorted_tickers[-10:]):
        if t["signal"] == "bearish":
            fb_str = f"{t['finbert_score']:.3f}" if t['finbert_score'] is not None else "N/A"
            print(f"  {t['ticker']}: {t['combined_score']:.3f} "
                  f"(RB: {t['rule_based_score']:.3f}, FB: {fb_str})")

    return output


if __name__ == "__main__":
    main()
