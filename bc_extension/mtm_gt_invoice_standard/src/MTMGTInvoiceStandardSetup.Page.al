page 71100 "MTM GT Invoice Std. Setup"
{
    PageType = Card;
    ApplicationArea = All;
    UsageCategory = Administration;
    Caption = 'MTM GT Invoice Standard Setup';
    SourceTable = "Company Information";
    InsertAllowed = false;
    DeleteAllowed = false;
    ModifyAllowed = false;

    layout
    {
        area(Content)
        {
            group(StandardLayout)
            {
                Caption = 'Standard Invoice Layout';

                field(ReportId; ReportIdTxt)
                {
                    ApplicationArea = All;
                    Caption = 'Invoice Report';
                    Editable = false;
                }
                field(LayoutName; LayoutNameTxt)
                {
                    ApplicationArea = All;
                    Caption = 'Invoice Layout';
                    Editable = false;
                }
                field(OutputRule; OutputRuleTxt)
                {
                    ApplicationArea = All;
                    Caption = 'Routing Rule';
                    Editable = false;
                    MultiLine = true;
                }
            }
        }
    }

    actions
    {
        area(Processing)
        {
            action(ApplyRouting)
            {
                ApplicationArea = All;
                Caption = 'Apply Invoice Routing';
                Image = Setup;
                ToolTip = 'Routes sales invoice print, PDF, and email attachment selections to the approved MTM GT invoice layout.';

                trigger OnAction()
                var
                    Mgt: Codeunit "MTM GT Invoice Std. Mgt.";
                begin
                    Mgt.ApplyInvoiceLayoutRouting();
                    Message('MTM GT invoice routing has been applied.');
                end;
            }
        }
    }

    trigger OnOpenPage()
    begin
        Rec.Get();
        ReportIdTxt := '50105 - FacturaGTM';
        LayoutNameTxt := 'MTMGTInvoiceStandard202606OnePage';
        OutputRuleTxt := 'Use this same visual layout for posted invoice print/PDF/email output and for draft/pro forma invoice output. External certifier/FEL portals must use their own matching provider template if they bypass Business Central report rendering.';
    end;

    var
        ReportIdTxt: Text[80];
        LayoutNameTxt: Text[80];
        OutputRuleTxt: Text[250];
}
