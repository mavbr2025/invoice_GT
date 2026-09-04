page 71014 "MTM Manual Inv Email Setup"
{
    Caption = 'MTM Manual Invoice Email Setup';
    PageType = Card;
    SourceTable = "MTM Manual Inv Email Setup";
    SourceTableView = where("Primary Key" = const(''));
    ApplicationArea = All;
    UsageCategory = Administration;
    InsertAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata "MTM Manual Inv Email Setup" = RM;

    layout
    {
        area(Content)
        {
            group(Control)
            {
                Caption = 'Control';

                field(CaptureEnabled; Rec."Capture Enabled")
                {
                    ApplicationArea = All;
                    Editable = false;
                    ToolTip = 'Specifies whether newly posted invoices are added to the downstream email queue.';
                }
                field(CustomerSendEnabled; Rec."Customer Send Enabled")
                {
                    ApplicationArea = All;
                    Editable = false;
                    ToolTip = 'Specifies whether stamped queued invoices may be emailed to customers.';
                }
                field(LastActivatedAt; Rec."Last Activated At")
                {
                    ApplicationArea = All;
                    Editable = false;
                }
                field(LastActivatedBy; Rec."Last Activated By")
                {
                    ApplicationArea = All;
                    Editable = false;
                }
            }
            group(Timing)
            {
                Caption = 'Timing and Limits';

                field(PollIntervalMinutes; Rec."Poll Interval Minutes")
                {
                    ApplicationArea = All;
                }
                field(StampWaitTimeoutMinutes; Rec."Stamp Wait Timeout Minutes")
                {
                    ApplicationArea = All;
                }
                field(InitialDelaySeconds; Rec."Initial Delay Seconds")
                {
                    ApplicationArea = All;
                }
                field(MaximumEntriesPerRun; Rec."Maximum Entries Per Run")
                {
                    ApplicationArea = All;
                }
            }
        }
    }

    actions
    {
        area(Processing)
        {
            action(PrepareCaptureOnly)
            {
                Caption = 'Start Capture Only';
                ApplicationArea = All;
                Image = Start;

                trigger OnAction()
                var
                    SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
                begin
                    SetupMgt.PrepareCaptureOnly();
                    Rec.Get('');
                    CurrPage.Update(false);
                    Message('Newly posted invoices will be queued. Customer email remains disabled.');
                end;
            }
            action(EnableCustomerSend)
            {
                Caption = 'Enable Customer Send';
                ApplicationArea = All;
                Image = SendMail;

                trigger OnAction()
                var
                    SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
                begin
                    if not Confirm(
                        'Enable automatic customer email for newly posted Guatemala invoices after FEL Stamp Received?',
                        false)
                    then
                        exit;

                    SetupMgt.EnableCustomerSend();
                    Rec.Get('');
                    CurrPage.Update(false);
                end;
            }
            action(DisableCustomerSend)
            {
                Caption = 'Disable Customer Send';
                ApplicationArea = All;
                Image = Stop;

                trigger OnAction()
                var
                    SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
                begin
                    SetupMgt.DisableCustomerSend();
                    Rec.Get('');
                    CurrPage.Update(false);
                end;
            }
            action(DisableAll)
            {
                Caption = 'Disable All';
                ApplicationArea = All;
                Image = Cancel;

                trigger OnAction()
                var
                    SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
                begin
                    SetupMgt.DisableAll();
                    Rec.Get('');
                    CurrPage.Update(false);
                end;
            }
            action(EnsureJobQueue)
            {
                Caption = 'Create or Verify Job Queue';
                ApplicationArea = All;
                Image = Job;

                trigger OnAction()
                var
                    SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
                begin
                    SetupMgt.EnsureJobQueue(Rec);
                    Message('The MTM manual invoice email job queue is available.');
                end;
            }
            action(ProcessNow)
            {
                Caption = 'Process Due Entries Now';
                ApplicationArea = All;
                Image = Refresh;

                trigger OnAction()
                var
                    Worker: Codeunit "MTM Manual Inv Email Worker";
                begin
                    Worker.ProcessDueEntries();
                    Message('Due queue entries were processed under the current send gate.');
                end;
            }
            action(OpenQueue)
            {
                Caption = 'Open Invoice Email Queue';
                ApplicationArea = All;
                Image = List;
                RunObject = page "MTM Manual Inv Email Queue";
            }
        }
    }

    trigger OnOpenPage()
    var
        SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
    begin
        SetupMgt.EnsureSetup(Rec);
    end;
}
