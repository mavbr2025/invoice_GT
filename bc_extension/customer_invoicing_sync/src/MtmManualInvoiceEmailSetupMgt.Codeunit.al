codeunit 71014 "MTM Manual Inv Email Setup Mgt"
{
    Permissions =
        tabledata "MTM Manual Inv Email Setup" = RIMD,
        tabledata "MTM Manual Inv Email Queue" = RIMD,
        tabledata "Job Queue Entry" = RIMD;

    procedure EnsureSetup(var Setup: Record "MTM Manual Inv Email Setup")
    begin
        if Setup.Get('') then
            exit;

        Setup.Init();
        Setup."Primary Key" := '';
        Setup."Capture Enabled" := false;
        Setup."Customer Send Enabled" := false;
        Setup."Poll Interval Minutes" := 2;
        Setup."Stamp Wait Timeout Minutes" := 120;
        Setup."Initial Delay Seconds" := 60;
        Setup."Maximum Entries Per Run" := 25;
        Setup.Insert(true);
    end;

    procedure PrepareCaptureOnly()
    var
        Setup: Record "MTM Manual Inv Email Setup";
    begin
        EnsureSetup(Setup);
        Setup."Capture Enabled" := true;
        Setup."Customer Send Enabled" := false;
        Setup."Last Activated At" := CurrentDateTime();
        Setup."Last Activated By" := CopyStr(UserId(), 1, MaxStrLen(Setup."Last Activated By"));
        Setup.Modify(true);
        EnsureJobQueue(Setup);
    end;

    procedure EnableCustomerSend()
    var
        Queue: Record "MTM Manual Inv Email Queue";
        Setup: Record "MTM Manual Inv Email Setup";
    begin
        EnsureSetup(Setup);
        Setup."Capture Enabled" := true;
        Setup."Customer Send Enabled" := true;
        Setup."Last Activated At" := CurrentDateTime();
        Setup."Last Activated By" := CopyStr(UserId(), 1, MaxStrLen(Setup."Last Activated By"));
        Setup.Modify(true);

        Queue.SetRange(Status, Queue.Status::ReadyToSend);
        Queue.ModifyAll("Next Attempt At", CurrentDateTime(), true);
        EnsureJobQueue(Setup);
    end;

    procedure DisableCustomerSend()
    var
        Setup: Record "MTM Manual Inv Email Setup";
    begin
        EnsureSetup(Setup);
        Setup."Customer Send Enabled" := false;
        Setup.Modify(true);
    end;

    procedure DisableAll()
    var
        Setup: Record "MTM Manual Inv Email Setup";
    begin
        EnsureSetup(Setup);
        Setup."Capture Enabled" := false;
        Setup."Customer Send Enabled" := false;
        Setup.Modify(true);
    end;

    procedure EnsureJobQueue(Setup: Record "MTM Manual Inv Email Setup")
    var
        JobQueueEntry: Record "Job Queue Entry";
    begin
        JobQueueEntry.SetRange("Object Type to Run", JobQueueEntry."Object Type to Run"::Codeunit);
        JobQueueEntry.SetRange("Object ID to Run", Codeunit::"MTM Manual Inv Email Worker");
        if JobQueueEntry.FindFirst() then begin
            case JobQueueEntry.Status of
                JobQueueEntry.Status::Error,
                JobQueueEntry.Status::"On Hold",
                JobQueueEntry.Status::Finished,
                JobQueueEntry.Status::"On Hold with Inactivity Timeout":
                    JobQueueEntry.SetStatus(JobQueueEntry.Status::Ready);
            end;
            exit;
        end;

        JobQueueEntry.Init();
        JobQueueEntry.ID := CreateGuid();
        JobQueueEntry."Object Type to Run" := JobQueueEntry."Object Type to Run"::Codeunit;
        JobQueueEntry."Object ID to Run" := Codeunit::"MTM Manual Inv Email Worker";
        JobQueueEntry.Description := 'MTM GT manual invoice customer email';
        JobQueueEntry."Recurring Job" := true;
        JobQueueEntry."No. of Minutes between Runs" := Setup."Poll Interval Minutes";
        JobQueueEntry."Run on Mondays" := true;
        JobQueueEntry."Run on Tuesdays" := true;
        JobQueueEntry."Run on Wednesdays" := true;
        JobQueueEntry."Run on Thursdays" := true;
        JobQueueEntry."Run on Fridays" := true;
        JobQueueEntry."Run on Saturdays" := true;
        JobQueueEntry."Run on Sundays" := true;
        JobQueueEntry."Earliest Start Date/Time" := CurrentDateTime() + 60000;
        JobQueueEntry."Maximum No. of Attempts to Run" := 3;
        JobQueueEntry."Rerun Delay (sec.)" := 60;
        JobQueueEntry.Insert(true);
        JobQueueEntry.SetStatus(JobQueueEntry.Status::Ready);
    end;
}
