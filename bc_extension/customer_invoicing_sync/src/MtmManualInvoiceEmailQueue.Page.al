page 71015 "MTM Manual Inv Email Queue"
{
    Caption = 'MTM Manual Invoice Email Queue';
    PageType = List;
    SourceTable = "MTM Manual Inv Email Queue";
    SourceTableView = sorting(Status, "Next Attempt At");
    ApplicationArea = All;
    UsageCategory = Lists;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions =
        tabledata "MTM Manual Inv Email Queue" = RM,
        tabledata "Sales Invoice Header" = R;

    layout
    {
        area(Content)
        {
            repeater(Queue)
            {
                field(Status; Rec.Status) { ApplicationArea = All; }
                field(PostedInvoiceNo; Rec."Posted Invoice No.") { ApplicationArea = All; }
                field(CustomerNo; Rec."Customer No.") { ApplicationArea = All; }
                field(ExternalDocumentNo; Rec."External Document No.") { ApplicationArea = All; }
                field(EnqueuedAt; Rec."Enqueued At") { ApplicationArea = All; }
                field(NextAttemptAt; Rec."Next Attempt At") { ApplicationArea = All; }
                field(StampWaitDeadline; Rec."Stamp Wait Deadline") { ApplicationArea = All; }
                field(StampCheckCount; Rec."Stamp Check Count") { ApplicationArea = All; }
                field(SendAttemptCount; Rec."Send Attempt Count") { ApplicationArea = All; }
                field(LastAttemptAt; Rec."Last Attempt At") { ApplicationArea = All; }
                field(SentAt; Rec."Sent At") { ApplicationArea = All; }
                field(LastErrorText; Rec."Last Error Text") { ApplicationArea = All; }
                field(CapturedBy; Rec."Captured By") { ApplicationArea = All; }
            }
        }
    }

    actions
    {
        area(Processing)
        {
            action(RetrySelected)
            {
                Caption = 'Reset Selected for Operator Retry';
                ApplicationArea = All;
                Image = ReOpen;

                trigger OnAction()
                var
                    SelectedQueue: Record "MTM Manual Inv Email Queue";
                    Worker: Codeunit "MTM Manual Inv Email Worker";
                begin
                    CurrPage.SetSelectionFilter(SelectedQueue);
                    if SelectedQueue.FindSet(true) then
                        repeat
                            Worker.ResetForOperatorRetry(SelectedQueue);
                        until SelectedQueue.Next() = 0;
                    CurrPage.Update(false);
                end;
            }
            action(ProcessDueNow)
            {
                Caption = 'Process Due Entries Now';
                ApplicationArea = All;
                Image = Refresh;

                trigger OnAction()
                var
                    Worker: Codeunit "MTM Manual Inv Email Worker";
                begin
                    Worker.ProcessDueEntries();
                    CurrPage.Update(false);
                end;
            }
            action(OpenPostedInvoice)
            {
                Caption = 'Open Posted Invoice';
                ApplicationArea = All;
                Image = ViewDetails;

                trigger OnAction()
                var
                    PostedInvoice: Record "Sales Invoice Header";
                begin
                    if not PostedInvoice.GetBySystemId(Rec."Posted Invoice System Id") then
                        Error('The posted invoice no longer exists.');
                    Page.Run(Page::"Posted Sales Invoice", PostedInvoice);
                end;
            }
        }
    }
}
