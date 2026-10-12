"""Select original-order tasks with no previously admitted raw identity."""
PREFIX='tokenmatched-holdout240-20261008:'
def never_started(tasks,events):
    ids={task['id'] for task in tasks};assert len(ids)==len(tasks)
    records,attempted,responses={},set(),set()
    for event in events:
        key,status=event['call_key'],event['status']
        assert key.startswith(PREFIX) and status in ('started','ok','error','local_stop')
        task_id=key[len(PREFIX):].split(':',1)[0];assert task_id in ids
        previous=records.get(key)
        if status=='started':
            assert previous is None
            attempted.add(task_id)
        else:
            assert previous is not None and previous['status']=='started' and previous['request']==event['request']
        if status=='ok':
            assert event['response_id'] not in responses
            responses.add(event['response_id'])
        records[key]=event
    return [task for task in tasks if task['id'] not in attempted]
