"""Initial-response wrapper and separate overall/conditional holdout estimands."""
from analysis import comparison
from study import MODEL,execute_case
PREFIX='tokenmatched-holdout240-20261008:'

def execute_item(task,caller,score):
    response=caller(PREFIX+task['id']+':initial',{'model':MODEL,'messages':[{'role':'user','content':task['prompt']}],'max_tokens':2048,'temperature':0,'stream':False,'thinking':{'type':'disabled'}})
    if response.get('status')!='ok':
        return {'id':task['id'],'status':'missing','reason':'initial_failed_or_unknown_never_resent','initial_response':response,'whole_item_excluded':True}
    correct,feedback=score(task,response['content'])
    if correct:
        return {'id':task['id'],'status':'initial_correct','initial_response':response,'initial_correct':True,'SAT_ablation_eligible':False}
    eligible=task['family']=='sat' and 'clause_index' in feedback
    case={'task':task,'initial_content':response['content'],'initial_feedback':feedback,
          'retry_order':[arm for arm in task['retry_order'] if arm!='coarse' or eligible]}
    row=execute_case(case,caller)
    row.update(initial_response=response,initial_correct=False,initial_feedback=feedback,SAT_ablation_eligible=eligible)
    return row

def paired(pairs,planned):
    if planned:
        return comparison(pairs,planned)
    assert not pairs
    return {'planned':0,'valid':0,'not_complete':0,'full_only_correct':0,'control_only_correct':0,
            'difference':None,'exact_McNemar_two_sided':None,'planned_possible_outcome_difference_bounds_not_CI':None}

def summarize(results,tasks,score):
    assert len(tasks)==240 and len({task['id'] for task in tasks})==240
    by_id={task['id']:task for task in tasks}
    assert len({row['id'] for row in results})==len(results)
    overall,conditional,ablation=[],[],[]
    initial_observed=initial_correct=conditional_planned=sat_planned=0
    initial_seen=set()
    for row in results:
        task=by_id[row['id']]
        initial=row.get('initial_response',{})
        if initial.get('status')=='ok':
            initial_seen.add(row['id'])
            initial_observed+=1
            initial_correct+=score(task,initial['content'])[0]
        if row['status']=='initial_correct':
            assert score(task,initial['content'])[0]
            overall.append((True,True))
            continue
        eligible=row.get('SAT_ablation_eligible',False)
        sat_planned+=eligible
        conditional_planned+=row.get('initial_correct') is False
        if row['status']!='complete_primary_pair':
            continue
        correct={arm:score(task,response['content'])[0] for arm,response in row['responses'].items()}
        overall.append((correct['full'],correct['neutral']))
        conditional.append((correct['full'],correct['neutral']))
        if eligible and row['SAT_ablation_status']=='complete':
            ablation.append((correct['full'],correct['coarse']))
    unresolved_sat=sum(task['family']=='sat' and task['id'] not in initial_seen for task in tasks)
    primary=paired(overall,240)
    primary.update(full_correct=sum(full for full,neutral in overall),neutral_correct=sum(neutral for full,neutral in overall))
    return {'primary_overall240':primary,
            'conditional_repair':paired(conditional,conditional_planned),
            'exploratory_SAT_full_vs_coarse':paired(ablation,sat_planned),
            'SAT_eligibility_unresolved_initials':unresolved_sat,
            'SAT_possible_eligibility_denominator_range':[sat_planned,sat_planned+unresolved_sat],
            'initial':{'planned':240,'observed':initial_observed,'correct':initial_correct,'not_observed':240-initial_observed,
                       'possible_full240_accuracy_bounds_not_CI':[initial_correct/240,(initial_correct+240-initial_observed)/240]},
            'scope':'independent disjoint holdout240; overall primary and conditional repair separate; never pooled with prior samples'}
