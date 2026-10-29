"""Keep inference abstentions out of complete-case normal-control comparisons."""


def counts(values):
    return dict(positiveDocuments=sum(not v['normal'] for v in values),completeCorrectSourceDocuments=sum(v['completeExpectedSources'] for v in values),
                expectedSources=sum(len(v['expectedSources']) for v in values),correctSources=sum(len(v['correctSources']) for v in values),
                normalDocuments=sum(v['normal'] for v in values),scopedNormalAlerts=sum(v['scopedNormalAlert'] for v in values),
                normalAnySourceAlerts=sum(v['normal'] and bool(v['alerts']) for v in values),unjudgedSourceAlerts=sum(len(v['unjudgedAlerts']) for v in values))


def summarize_cases(rows):
    comparable=[r for r in rows if r['sources'] and r['allSelectedSourcesAssessed'] and all(s['result']['assessed'] for s in r['sources'])]
    ids={r['caseId'] for r in comparable};abstained=[r for r in rows if r['caseId'] not in ids]
    return dict(scope='Observed alerts across all cases; quality comparison only for completely assessed selected candidates, not full-library negatives',
                operationalAlertsWithAbstentions={key:counts([r[key] for r in rows]) for key in ('baseline','candidate')},
                completeSelectedCandidateComparison={key:counts([r[key] for r in comparable]) for key in ('baseline','candidate')},
                coverage=dict(totalDocuments=len(rows),comparableDocuments=len(comparable),abstainedDocuments=len(abstained),
                              abstainedNormalDocuments=sum(r['candidate']['normal'] for r in abstained),
                              abstainedPositiveDocuments=sum(not r['candidate']['normal'] for r in abstained),
                              comparableCaseIds=[r['caseId'] for r in comparable],abstainedCaseIds=[r['caseId'] for r in abstained]),
                normalPopulationFpr=None,independentNaturalQualityAccepted=False)
