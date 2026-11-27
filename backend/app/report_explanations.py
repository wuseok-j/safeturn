"""판정 원인은 AI 추측 대신 확정된 근거와 판단 이력으로 설명한다."""
CURRENT_VERSION = 2


def enrich(report):
    legacy = report.get('assessment_version', 1) < CURRENT_VERSION
    report['assessment_note'] = ('이 보고서는 이전 판정 기준으로 저장된 기록입니다. 점수는 당시 기록을 유지합니다. '
                                 '개선된 판정은 새 플레이에서 확인할 수 있습니다.' if legacy else '')
    timeline = report.get('timeline', [])
    for check in report['checks']:
        evidence = check.get('evidence', [])
        missing = [e['label'] for e in evidence if not e['met']]
        check['missing_actions'] = missing
        actions = [e for e in timeline if e['stage'] == check['stage']]
        risk_end = any(e['risk_after'] >= report['max_risk'] for e in actions)
        count = sum(e['met'] for e in evidence)
        if check['result'] == 'correct':
            reason = f'필수 행동 {len(evidence)}개를 모두 확인했습니다.' if evidence else '단계의 행동 기준을 확인했습니다.'
            code = 'completed'
        elif check['result'] == 'not_reached':
            reason, code = '이 단계에 도달하기 전에 플레이가 종료되어 평가하지 않았습니다.', 'not_reached'
        elif risk_end:
            reason, code = '위험도가 한도에 도달해 이 단계에서 플레이가 중단됐습니다.', 'risk_limit'
        else:
            reason = f'필수 행동 {len(evidence)}개 중 {count}개를 확인했습니다.'
            if missing:
                reason += ' 추가 확인이 필요한 행동: ' + ' · '.join(missing) + '.'
            code = 'missing_actions'
        check['reason'] = reason
        check['reason_code'] = code
        reviews = []
        for event in actions:
            if event['verdict'] == 'wrong':
                note = f'위험 행동으로 기록됨 · 위험도 +{max(0, event["risk_after"] - event["risk_before"])}'
            elif event['verdict'] == 'correct':
                note = '이 발언까지 반영해 단계의 필수 행동을 모두 확인했습니다.'
            else:
                note = '추가 확인 필요 · 필수 행동을 모두 확인하지 못했습니다. 위험 행동 판정은 아닙니다.'
            reviews.append({'text': event['action'], 'verdict': event['verdict'], 'note': note})
        check['action_reviews'] = reviews
    return report
